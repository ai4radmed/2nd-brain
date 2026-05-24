# secrets/

API 키·OAuth 토큰을 두는 폴더. **절대 git 에 올라가지 않음** (`.gitignore` 로 차단).

## 권한

```bash
chmod 700 secrets/
chmod 600 secrets/*
```

## 인증 방식

기본은 OAuth (`claude login`) — 첫 컨테이너 실행 시 한 번 로그인하면 `claude-state` named volume 에 영속. 이 폴더에 아무것도 둘 필요 없음.

## API 키 (옵션)

OAuth 대신 API 키를 쓰려면:

1. 키 파일 생성:
   ```bash
   echo "sk-ant-xxxx" > secrets/anthropic-key
   chmod 600 secrets/anthropic-key
   ```

2. `compose.yml` 의 각 서비스에 다음 추가:
   ```yaml
   environment:
     ANTHROPIC_API_KEY_FILE: /run/secrets/anthropic-key
   secrets:
     - anthropic-key
   ```

3. `compose.yml` 최하단에 secrets 정의 추가:
   ```yaml
   secrets:
     anthropic-key:
       file: ./secrets/anthropic-key
   ```

`entrypoint.sh` 가 `ANTHROPIC_API_KEY_FILE` 을 읽어 환경변수로 export 한다.
