# 한국 속보 뉴스 텔레그램 봇

9개 언론사(연합뉴스, YTN, MBC, KBS, 한국경제, 매일경제, 국민일보, 조선일보, 서울신문)의
속보를 5분마다 텔레그램으로 전송합니다.

## 설정 방법

### 1단계 — 이 저장소를 GitHub에 올리기

```bash
# GitHub에서 새 저장소(private 권장) 만들고:
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR_ID/YOUR_REPO.git
git push -u origin main
```

### 2단계 — GitHub Secrets 등록

저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| 이름 | 값 |
|------|----|
| `TELEGRAM_TOKEN` | 텔레그램 봇 토큰 (예: `123456:ABC-DEF...`) |
| `TELEGRAM_CHAT_ID` | 채팅 ID (예: `-1001234567890`) |

### 3단계 — Actions 활성화

저장소 → **Actions** 탭 → **"I understand my workflows, enable them"** 클릭

### 4단계 — 수동 테스트

Actions → **속보 뉴스 봇** → **Run workflow** 로 즉시 테스트 가능

## 주의사항

- GitHub Actions의 cron 최소 실행 단위는 **5분**입니다 (1분 불가)
- 무료 계정 기준 월 2,000분 제공 → 5분마다 실행 시 월 약 8,640분 필요
  → **Public 저장소**로 만들면 무제한 무료
- 속보가 없으면 텔레그램 메시지가 오지 않습니다 (정상)

## 텔레그램 봇 메시지 예시

```
🔴 [속보] 📰 연합뉴스 14:32
[속보] 정부, 긴급 경제대책 발표
기사 보기 →
```
