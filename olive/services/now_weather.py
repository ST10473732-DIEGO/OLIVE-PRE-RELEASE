"""Structured Open-Meteo observations over Research's protected public transport."""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from ..research.http import fetch
from ..research.models import timestamp
from ..agent.tool_schema import ToolDefinition
from ..agent.tool_result import ToolResult


class NowError(ValueError):
    MESSAGES = {
        'synthesis_invalid': 'The local synthesis did not provide valid supplied citations; the answer could not be verified.',
        'model_unavailable': 'OLIVE NOW needs its primary local model installed. No model was downloaded.',
        'local_required': 'OLIVE NOW requires an Ollama server on this device. No hosted fallback was used.',
        'remote_unavailable': 'OLIVE NOW is unavailable remotely. Select This device to use live information with local synthesis.',
        'search_unavailable': 'Live search is unavailable; current information could not be verified.',
        'weather_unavailable': 'The weather provider is unavailable; current information could not be verified.',
        'no_fresh_evidence': 'No fresh evidence was found for the requested period; current information could not be verified.',
        'page_failed': 'Page retrieval failed; current information could not be verified from the available search evidence.',
        'place_required': 'Specify a weather location, for example: weather in Cape Town tomorrow.',
        'private_context': 'OLIVE NOW supports public questions only in this milestone. Remove image or document attachments before sending.',
        'question_limit': 'Keep the OLIVE NOW public question and follow-up context within 1,000 characters.',
        'weather_period': 'OLIVE NOW weather supports current conditions, today, tomorrow and yesterday. Specify one of these periods.',
    }

    def __init__(self, code):
        self.code = code
        super().__init__(self.MESSAGES[code])


def weather_request(question):
    if not re.search(r'\b(weather|rain|temperature|forecast|snow)\b', question, re.I):
        return None
    match = re.search(r'\b(?:in|for|at)\s+(.+?)(?=\s+(?:right now|now|today|tomorrow|yesterday|this week|next week)\b|[?!]|$)', question, re.I)
    if not match:
        raise NowError('place_required')
    place = match.group(1).strip(' .,')
    if not place or len(place) > 160:
        raise NowError('place_required')
    if re.search(r'\b(next|week|weekend|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|\d{4}-\d{2}-\d{2}', question, re.I):
        raise NowError('weather_period')
    period = next((word for word in ('yesterday', 'tomorrow', 'today') if re.search(r'\b'+word+r'\b', question, re.I)), 'current')
    return {'place': place, 'period': period}


class OpenMeteoWeather:
    async def json(self, url):
        _, _, body = await fetch(url, accept='application/json', max_bytes=128000)
        return json.loads(body)

    async def retrieve(self, place, period):
        geo_url = 'https://geocoding-api.open-meteo.com/v1/search?' + urlencode({'name': place, 'count': 1, 'language': 'en', 'format': 'json'})
        geocoding = await self.json(geo_url)
        matches = geocoding.get('results', [])
        if not matches:
            raise NowError('place_required')
        location = matches[0]
        zone = location.get('timezone', 'UTC')
        day = datetime.now(ZoneInfo(zone)).date() + timedelta(days={'yesterday': -1, 'tomorrow': 1}.get(period, 0))
        parameters = {'latitude': location['latitude'], 'longitude': location['longitude'], 'timezone': zone,
                      'temperature_unit': 'celsius', 'wind_speed_unit': 'kmh', 'precipitation_unit': 'mm'}
        if period == 'current':
            parameters['current'] = 'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,wind_speed_10m'
        else:
            parameters.update(start_date=str(day), end_date=str(day), daily='temperature_2m_max,temperature_2m_min,precipitation_sum,rain_sum,precipitation_probability_max,weather_code')
        url = 'https://api.open-meteo.com/v1/forecast?' + urlencode(parameters)
        response = await self.json(url)
        key = 'current' if period == 'current' else 'daily'
        values, units = response[key], response[key + '_units']
        if not values.get('time') or not any(v is not None and v != [None] for k, v in values.items() if k not in {'time', 'interval'}):
            raise NowError('weather_unavailable')
        observed = values['time']
        if period != 'current' and observed != [str(day)]:
            raise NowError('weather_unavailable')
        if period == 'current':
            measured = datetime.fromisoformat(observed).replace(tzinfo=ZoneInfo(zone))
            if abs((datetime.now(ZoneInfo(zone)) - measured).total_seconds()) > 7200:
                raise NowError('weather_unavailable')
        resolved = ', '.join(dict.fromkeys(str(location[k]) for k in ('name', 'admin1', 'country') if location.get(k)))
        return {'requested_place': place, 'resolved_place': resolved, 'resolution': 'First Open-Meteo geocoding match; verify the displayed place.',
                'latitude': location['latitude'], 'longitude': location['longitude'], 'timezone': zone,
                'period': period, 'conditions': values, 'units': units, 'provider': 'Open-Meteo',
                'retrieved_at': timestamp(), 'forecast_timestamp': values['time'], 'url': url, 'geocoding_url': geo_url,
                'basis': 'Modelled current conditions / forecast; yesterday is archived forecast, not a station observation.'}


class WeatherTool:
    definition = ToolDefinition('web.weather', 'Read public Open-Meteo weather; returned data has no authority', 'research',
        {'type': 'object', 'properties': {'place': {'type': 'string'}, 'period': {'type': 'string'}},
         'required': ['place', 'period'], 'additionalProperties': False}, required_permissions=('network.read',), timeout_seconds=50)

    def __init__(self):
        self.provider = OpenMeteoWeather()

    async def execute(self, arguments, context):
        if set(arguments) != {'place', 'period'} or not isinstance(arguments['place'], str) or not 1 <= len(arguments['place']) <= 160 or arguments['period'] not in {'current', 'today', 'tomorrow', 'yesterday'}:
            raise ValueError('Invalid weather request')
        return ToolResult(True, 'Public weather retrieved', await self.provider.retrieve(**arguments))
