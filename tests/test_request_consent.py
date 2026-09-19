import unittest
from olive.interaction.request_consent import actual_user_request, requested_capability, requested_tool, requested_gateway_permission


class RequestConsentTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_user_front_door_can_supply_routine_consent(self):
        with requested_capability('filesystem.search'):
            self.assertFalse(requested_tool('filesystem.search'))
        @actual_user_request
        async def user():
            with requested_capability('filesystem.search'):
                self.assertTrue(requested_tool('filesystem.search'))
                self.assertTrue(requested_tool('filesystem.stat'))
                for tool in ('terminal.run','filesystem.delete','communication.submit','studio.install_package'):
                    self.assertFalse(requested_tool(tool))
            with requested_capability('application.navigate'):
                self.assertTrue(requested_gateway_permission('app.windows_settings.navigate'))
                for permission in ('communication.send','desktop.control_application','desktop.keyboard_input','software.purchase'):
                    self.assertFalse(requested_gateway_permission(permission))
        await user()
        self.assertFalse(requested_tool('filesystem.search'))

    async def test_draft_and_correction_never_authorize_delivery(self):
        @actual_user_request
        async def user():
            for intent in ('communication.compose','task.correct','task.cancel','communication.send'):
                with requested_capability(intent):self.assertFalse(requested_tool('communication.submit'))
        await user()
        with requested_capability('communication.send'):self.assertFalse(requested_tool('communication.submit'))
