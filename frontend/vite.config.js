// 개발 중 /api는 FastAPI(8000)로 넘김 → CORS 설정이 필요 없음
export default {
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
}
