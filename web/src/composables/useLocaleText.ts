import { useI18n } from 'vue-i18n'

/**
 * 双语文案选择：当当前语言为英文(en-US)时，优先返回字段的英文版（field + '_en'），
 * 否则回退到默认字段。用于 skill / MCP 连接器 / 工具 等数据驱动的描述与名称。
 *
 * 数据模型：每条记录同时携带 `description` / `description_en`（可选）、`name` / `name_en`（可选）。
 * 英文环境下若英文版为空则回退中文，保证总有文案可显示。
 */
export function useLocaleText() {
  const { locale } = useI18n()

  function pickEn(item: any, field: string = 'description'): string {
    const obj = item || {}
    if (locale.value === 'en-US') {
      const en = obj[`${field}_en`]
      if (en && String(en).trim()) return en
    }
    return obj[field] || ''
  }

  return { pickEn }
}
