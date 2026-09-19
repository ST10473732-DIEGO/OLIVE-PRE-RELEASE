import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from olive.bridge.agent_routes import history as agent_history
from olive.bridge.research_routes import history as research_history


class HistoryPageTests(unittest.TestCase):
    def test_older_agent_records_remain_searchable_and_pageable(self):
        records=[{'id':str(i),'user_request':f'Fixture task {i}'} for i in range(125)]
        services=SimpleNamespace(agent=SimpleNamespace(history=Mock(return_value=records)))
        self.assertEqual(len(agent_history(services)),100)
        self.assertEqual(agent_history(services,offset=100)[-1]['id'],'124')
        self.assertEqual(agent_history(services,query='TASK 124')[0]['id'],'124')
        with self.assertRaises(ValueError):agent_history(services,offset=-1)

    def test_research_search_precedes_page_limit_and_omits_report_payload(self):
        records=[{'id':str(i),'question':f'Fixture question {i}','final_report':'large body'} for i in range(125)]
        services=SimpleNamespace(research=SimpleNamespace(history=Mock(return_value=records)))
        result=research_history(services,query='question 124')
        self.assertEqual(result[0]['id'],'124')
        self.assertNotIn('final_report',result[0])
