const AUTH_DETAIL_MAP: Record<string, string> = {
  missing_authorization: "Отсутствует токен",
  bad_scheme: "Неверная схема авторизации",
  invalid_token: "Неверный токен",
  token_not_initialized: "Сессионный токен не инициализирован"
};

export function formatAuthDetail(detail?: string | null): string | null {
  if (!detail) return null;
  const key = detail.trim();
  return AUTH_DETAIL_MAP[key] ?? detail;
}
