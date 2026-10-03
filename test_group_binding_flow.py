import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot


class GroupBindingFlowTests(unittest.TestCase):
    def setUp(self):
        self.legacy = bot.reference.SiteConfig("zk", "科大", "https://example.test:1777", frozenset({84801506}))
        self.spiritual = bot.reference.SiteConfig("cedar-spiritual", "香柏木门训 / YDS_HZ灵命组", "https://example.test/api/bot/groups/spiritual", frozenset({85001808}))
        self.service = bot.reference.SiteConfig("cedar-service", "香柏木门训 / YDS_HZ事奉组", "https://example.test/api/bot/groups/service", frozenset())
        self.sites = (self.legacy, self.spiritual, self.service)
        self.state = {
            "potato_chat_types": {"84801506": 3, "85001808": 3, "85002311": 3, "84973209": 3},
            "potato_chat_names": {"84801506": "科大门训小组", "85001808": "个人灵命组",
                                  "85002311": "HZ🚪训JH侍奉组", "84973209": "test"},
        }
        bot.group_binding_flows.clear()
        self.patches = [
            patch.object(bot.reference, "SITES", self.sites),
            patch.object(bot.reference, "SITE_BY_ID", {site.site_id: site for site in self.sites}),
            patch.object(bot.reference, "SITE_BY_CHAT_ID", {84801506: self.legacy, 85001808: self.spiritual}),
            patch.object(bot.reference, "state", self.state),
            patch.object(bot.reference, "is_super_admin", return_value=True),
            patch.object(bot.reference, "send"),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for item in reversed(self.patches):
            item.stop()
        bot.group_binding_flows.clear()

    def test_name_match_requires_confirmation_before_binding(self):
        group = SimpleNamespace(chat_type=bot._ChatType.GROUP, self_in_group=True)
        with patch.object(bot.bot.rpc, "get_full_chat_by_id", return_value=group), patch.object(bot.reference, "bind_group_to_site") as bind:
            self.assertTrue(bot._handle_group_binding_flow(900, 77, "管理员 绑定群"))
            prompt = bot.reference.send.call_args.args[3]
            self.assertIn("85002311", prompt)
            self.assertNotIn("84801506", prompt)
            self.assertNotIn("科大门训小组", prompt)
            self.assertTrue(bot._handle_group_binding_flow(900, 77, "2"))
            self.assertIn("YDS_HZ事奉组", bot.reference.send.call_args.args[3])
            bind.assert_not_called()
            self.assertTrue(bot._handle_group_binding_flow(900, 77, "确认"))
            bind.assert_called_once_with(self.service, 85002311)
            self.assertNotIn(900, bot.group_binding_flows)

    def test_potato_renders_cedar_reader_title_as_link(self):
        text = "📖 灵命组\n[今日灵修](https://example.test/?reader_source=%2Fapi%2Fassets%2F473%2Frange%3Fpages%3D36-37&reader_group=spiritual)"
        with patch.object(bot, "potato_api") as api:
            bot.bot.rpc.send_msg(1, 85001808, bot._MessageData(text=text))
            payload = api.call_args.args[1]
            self.assertEqual(payload["text"], text)
            self.assertTrue(payload["markdown"])
            bot.bot.rpc.send_msg(1, 85001808, bot._MessageData(text="普通提醒"))
            self.assertNotIn("markdown", api.call_args.args[1])

    def test_unmatched_group_lists_only_cedar_sites_and_can_cancel(self):
        with patch.object(bot.reference, "bind_group_to_site") as bind:
            bot._handle_group_binding_flow(900, 77, "管理员 绑定群")
            bot._handle_group_binding_flow(900, 77, "1")
            prompt = bot.reference.send.call_args.args[3]
            self.assertIn("YDS_HZ灵命组", prompt)
            self.assertIn("YDS_HZ事奉组", prompt)
            self.assertNotIn("科大门训小组", prompt)
            bot._handle_group_binding_flow(900, 77, "取消")
            bind.assert_not_called()
            self.assertNotIn(900, bot.group_binding_flows)

    def test_unbind_lists_only_cedar_bindings_and_requires_confirmation(self):
        with patch.object(bot.reference, "unbind_group_from_site") as unbind:
            bot._handle_group_binding_flow(900, 77, "管理员 解绑群")
            prompt = bot.reference.send.call_args.args[3]
            self.assertIn("85001808", prompt)
            self.assertNotIn("84801506", prompt)
            bot._handle_group_binding_flow(900, 77, "1")
            unbind.assert_not_called()
            bot._handle_group_binding_flow(900, 77, "确认")
            unbind.assert_called_once_with(self.spiritual, 85001808)

    def test_group_name_suggestions_are_scoped_to_cedar(self):
        self.assertIsNone(bot._suggest_site(84801506))
        self.assertIs(bot._suggest_site(85001808), self.spiritual)
        self.assertIs(bot._suggest_site(85002311), self.service)

    def test_old_direct_binding_syntax_opens_cedar_guide(self):
        with patch.object(bot.reference, "bind_group_to_site") as bind:
            self.assertTrue(bot._handle_group_binding_flow(900, 77, "管理员 绑定群：科大 84973209"))
            bind.assert_not_called()
            self.assertIn("选择要绑定的群", bot.reference.send.call_args.args[3])

    def test_private_message_enters_guide_before_legacy_command_handler(self):
        update = {"message": {"chat": {"id": 900, "type": 1}, "from": {"id": 77}, "text": "管理员 绑定群"}}
        with patch.object(bot.reference, "save_state"), patch.object(bot.reference.cli, "new_message") as legacy:
            bot.dispatch(update)
        legacy.assert_not_called()
        self.assertIn(900, bot.group_binding_flows)


if __name__ == "__main__":
    unittest.main()
