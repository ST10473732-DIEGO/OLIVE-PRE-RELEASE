"""Real installed-toolchain acceptance, isolated data and loopback only."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse


async def main():
    with tempfile.TemporaryDirectory(prefix='olive-studio-services-') as temporary:
        root = Path(temporary)
        async def deny(request):
            return ConfirmationResponse(False)
        services = ServiceContainer(lambda *args: None, deny, root/'profile', migrate=False)
        tooling = services.studio_tooling
        try:
            console = await tooling.new_project('csharp', 'console', 'ConsoleApp', str(root))
            wid = console['workspace']['id']
            buffer = services.studio.service(wid)
            buffer.open_file('Program.cs')
            buffer.update('Program.cs', '// retained unsaved console buffer\n')
            python = await tooling.new_project('python', 'console', 'PythonApp', str(root))
            pid = python['workspace']['id']
            assert pid != wid and buffer.open_files['Program.cs'].unsaved
            assert 'retained' not in (root/'ConsoleApp/Program.cs').read_text()
            # Clear sources only in these new fixture projects: all needed SDK assets are installed.
            (root/'ConsoleApp/NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
            run = await tooling.run(wid)
            result = await asyncio.wait_for(services.run_service.wait(run['session_id']), 90)
            assert result.exit_code == 0 and 'Hello, World!' in result.stdout, result.to_dict()
            job = await tooling.test(pid)
            await asyncio.wait_for(tooling.jobs[job['id']]['task'], 60)
            test = tooling._job_summary(tooling.jobs[job['id']])
            assert test['state'] == 'completed', test
            api = await tooling.new_project('csharp', 'webapi', 'WebApp', str(root))
            aid = api['workspace']['id']
            (root/'WebApp/NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
            config = tooling.config_get(aid)
            # Keep fixture logging in its captured console; no Windows Event Log writes.
            config['environment'] = {'ASPNETCORE_URLS': 'http://127.0.0.1:0', 'Logging__EventLog__LogLevel__Default': 'None'}
            tooling.config_save(aid, config)
            assert tooling.config_get(pid)['environment'] == {}, 'Environment leaked between workspaces'
            launched = await tooling.run(aid)
            session = services.run_service.sessions[launched['session_id']]
            for _ in range(600):
                if session.local_url or session.state not in {'starting', 'running'}: break
                await asyncio.sleep(.1)
            assert session.local_url, session.to_dict()
            response = await tooling.web_request(aid, session.id, 'GET', '/weatherforecast')
            assert response['status'] == 200, {'response': response, 'run': session.to_dict()}
            forecasts = json.loads(response['body'])
            assert len(forecasts) == 5 and all('temperatureC' in x for x in forecasts), forecasts
            await services.run_service.stop(session.id)
            print(json.dumps({'classification': 'actual Studio registered tools, SDK builds, processes and loopback HTTP',
                              'independent_workspaces': 3, 'dirty_console_buffer_retained': True,
                              'console_output': result.stdout.strip(), 'python_test': test,
                              'aspnet_status': response['status'], 'forecast_count': len(forecasts)}, indent=2))
        finally:
            await services.shutdown()

if __name__ == '__main__': asyncio.run(main())
