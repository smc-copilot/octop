/**
 * Minimal Admin market policy panel: show market_mode + list/add/remove slug rules.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { Plus, RefreshCw, Store, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  marketPolicyApi,
  type MarketEffect,
  type MarketPolicyRule,
  type MarketResourceType,
} from "../../../api/modules/marketPolicy";
import { userGroupsApi, type UserGroup } from "../../../api/modules/userGroups";
import { message } from "@/utils/antdMessage";
import { apiErrorMessage } from "../../../utils/apiError";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import tabStyles from "../AdvancedSettings/tabContent.module.less";

const { Text } = Typography;

interface RuleFormValues {
  resource_type: MarketResourceType;
  slug: string;
  effect: MarketEffect;
  user_group_id?: string | null;
  priority?: number;
}

export default function MarketPolicyPanel() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [marketMode, setMarketMode] = useState("public");
  const [rules, setRules] = useState<MarketPolicyRule[]>([]);
  const [groups, setGroups] = useState<UserGroup[]>([]);
  const [form] = Form.useForm<RuleFormValues>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [policy, groupRows] = await Promise.all([
        marketPolicyApi.list(),
        userGroupsApi.list().catch(() => [] as UserGroup[]),
      ]);
      setMarketMode(policy.market_mode);
      setRules(policy.rules);
      setGroups(groupRows);
    } catch (err) {
      message.error(apiErrorMessage(err, t("security.marketLoadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onCreate = async () => {
    let values: RuleFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setSaving(true);
    try {
      await marketPolicyApi.createRule({
        resource_type: values.resource_type,
        slug: values.slug.trim(),
        effect: values.effect,
        user_group_id: values.user_group_id || null,
        priority: values.priority ?? 0,
      });
      form.resetFields();
      form.setFieldsValue({
        resource_type: "skill",
        effect: "allow",
        priority: 0,
      });
      message.success(t("security.marketRuleAdded"));
      await load();
    } catch (err) {
      message.error(apiErrorMessage(err, t("security.marketRuleAddFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (ruleId: string) => {
    try {
      await marketPolicyApi.deleteRule(ruleId);
      message.success(t("security.marketRuleDeleted"));
      await load();
    } catch (err) {
      message.error(
        apiErrorMessage(err, t("security.marketRuleDeleteFailed"), t),
      );
    }
  };

  return (
    <div className={tabStyles.panel}>
      <TabPanelHeader
        icon={<Store size={22} />}
        title={t("security.marketTitle")}
        description={t("security.marketDesc")}
      />
      <Space style={{ marginBottom: 16 }} wrap>
        <Text>
          {t("security.marketModeLabel")}:{" "}
          <Tag color="blue">{marketMode}</Tag>
        </Text>
        <Text type="secondary">{t("security.marketModeHint")}</Text>
        <Button
          icon={<RefreshCw size={14} />}
          onClick={() => void load()}
          loading={loading}
        >
          {t("common.refresh")}
        </Button>
      </Space>

      <Form
        form={form}
        layout="inline"
        style={{ marginBottom: 16, rowGap: 8 }}
        initialValues={{
          resource_type: "skill",
          effect: "allow",
          priority: 0,
        }}
      >
        <Form.Item
          name="resource_type"
          rules={[{ required: true }]}
          label={t("security.marketResourceType")}
        >
          <Select
            style={{ width: 120 }}
            options={[
              { value: "skill", label: "skill" },
              { value: "skillset", label: "skillset" },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="slug"
          rules={[{ required: true, message: t("security.marketSlugRequired") }]}
          label={t("security.marketSlug")}
        >
          <Input placeholder="slug" style={{ width: 180 }} />
        </Form.Item>
        <Form.Item
          name="effect"
          rules={[{ required: true }]}
          label={t("security.marketEffect")}
        >
          <Select
            style={{ width: 110 }}
            options={[
              { value: "allow", label: "allow" },
              { value: "deny", label: "deny" },
            ]}
          />
        </Form.Item>
        <Form.Item name="user_group_id" label={t("security.marketGroup")}>
          <Select
            allowClear
            style={{ width: 160 }}
            placeholder={t("security.marketGroupGlobal")}
            options={groups.map((g) => ({
              value: g.user_group_id,
              label: g.name,
            }))}
          />
        </Form.Item>
        <Form.Item name="priority" label={t("security.marketPriority")}>
          <InputNumber style={{ width: 90 }} />
        </Form.Item>
        <Form.Item>
          <Button
            type="primary"
            icon={<Plus size={14} />}
            loading={saving}
            onClick={() => void onCreate()}
          >
            {t("security.marketAddRule")}
          </Button>
        </Form.Item>
      </Form>

      <Table
        rowKey="id"
        loading={loading}
        dataSource={rules}
        pagination={{ pageSize: 20 }}
        columns={[
          {
            title: t("security.marketResourceType"),
            dataIndex: "resource_type",
            width: 110,
          },
          { title: t("security.marketSlug"), dataIndex: "slug" },
          {
            title: t("security.marketEffect"),
            dataIndex: "effect",
            width: 90,
            render: (effect: string) => (
              <Tag color={effect === "deny" ? "red" : "green"}>{effect}</Tag>
            ),
          },
          {
            title: t("security.marketGroup"),
            dataIndex: "user_group_id",
            render: (id: string | null) =>
              id
                ? groups.find((g) => g.user_group_id === id)?.name || id
                : t("security.marketGroupGlobal"),
          },
          {
            title: t("security.marketPriority"),
            dataIndex: "priority",
            width: 90,
          },
          {
            title: t("common.actions"),
            width: 80,
            render: (_: unknown, row: MarketPolicyRule) => (
              <Popconfirm
                title={t("security.marketDeleteConfirm")}
                onConfirm={() => void onDelete(row.id)}
              >
                <Button
                  type="text"
                  danger
                  icon={<Trash2 size={14} />}
                  aria-label={t("common.delete")}
                />
              </Popconfirm>
            ),
          },
        ]}
      />
    </div>
  );
}
