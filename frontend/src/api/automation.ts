import { http } from './client'

export type AutomationStrategyId =
  | 'main_force'
  | 'low_price_bull'
  | 'small_cap'
  | 'profit_growth'
  | 'value_stock'

export interface AutomationStrategySetting {
  enabled: boolean
  filters: Record<string, unknown>
}

export interface AutomationSettings {
  screener_enabled: boolean
  analysis_enabled: boolean
  screener_run_hour: number
  screener_run_minute: number
  analysis_run_hour: number
  analysis_run_minute: number
  strategy_settings: Partial<Record<AutomationStrategyId, AutomationStrategySetting>>
  email_notify_enabled: boolean
  notify_email: string | null
  updated_at: string | null
}

export interface AutomationSettingsUpdate {
  screener_enabled: boolean
  analysis_enabled: boolean
  screener_run_hour: number
  screener_run_minute: number
  analysis_run_hour: number
  analysis_run_minute: number
  strategy_settings: Partial<Record<AutomationStrategyId, AutomationStrategySetting>>
  email_notify_enabled: boolean
  notify_email: string | null
}

export const automationApi = {
  getSettings(): Promise<{ data: AutomationSettings }> {
    return http.get('/automation/settings')
  },
  updateSettings(payload: AutomationSettingsUpdate): Promise<{ data: AutomationSettings }> {
    return http.put('/automation/settings', payload)
  },
}
