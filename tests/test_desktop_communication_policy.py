import unittest
from types import SimpleNamespace
from olive.desktop.communication_policy import require_supported_ui_sender


class DesktopCommunicationPolicyTests(unittest.TestCase):
    def test_discord_variants_and_real_hosts_require_manual_personal_send(self):
        for name,window,url in [('Discord',{},''),('Other',{'executable':r'C:\fixture\DiscordCanary.exe'},''),
                                ('Other',{'title':'general - Discord'},''),('Browser',{},'https://canary.discord.com/channels/1/2')]:
            with self.subTest(name=name,window=window,url=url),self.assertRaisesRegex(PermissionError,'manually'):
                require_supported_ui_sender(SimpleNamespace(identity=SimpleNamespace(display_name=name),window=window),url)
        require_supported_ui_sender(SimpleNamespace(identity=SimpleNamespace(display_name='Owned fixture'),window={}),
                                    'https://discord.com.example.invalid/')
