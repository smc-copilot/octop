# mail-client

可配置的 **POP3 收信 + SMTP 纯文本发信** 工具插件（`kind=tool`）。

- 后端：`mail_list` / `mail_read` / `mail_send` / `mail_probe`
- 前端：预构建 `ui/dist/`，聊天卡片渲染收件箱、正文、发信结果、连通性
- 配置：Dashboard「工具管理」填写 POP3/SMTP（密码字段为 `password`，不会回传到模型）

安装与字段说明见 [`feature/docs/mail-client-plugin.md`](../../feature/docs/mail-client-plugin.md)。

```bash
octop plugin install ./plugins/mail-client --force
```
