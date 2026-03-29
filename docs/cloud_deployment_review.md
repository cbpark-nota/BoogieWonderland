# Flutter Web 클라우드 배포 방안 검토

## 1. 요구사항
- 커스텀 도메인으로 배포
- 클라우드 무료 티어만 사용, 과도한 트래픽 시 비용 발생 방지
- 다중 사용자 지원 (각자 포트폴리오 업로드)
- 보안: 악성 파일 업로드 방지

## 2. 서비스별 비교

### Cloudflare Pages (추천 1위)
- 비용: 완전 무료, 대역폭 무제한
- DDoS 방어: 기본 포함 (Shield Standard)
- 커스텀 도메인: 무료 + 자동 SSL
- 트래픽 초과 시: 비용 발생 안 함 (무제한)
- 빌드: 월 500회 무료
- GitHub 연동 자동 배포 지원

### Firebase Hosting (추천 2위)
- 비용: Spark 플랜 무료 (10GB 저장, 360MB/일 전송)
- 설정: 가장 간단 (Firebase CLI)
- 트래픽 초과 시: 서비스 중단 (비용 발생 안 함)

### AWS S3 + CloudFront (추천 3위)
- 비용: 정액 Free 플랜 $0/월
- Budget Alert으로 비용 상한 설정 가능
- 설정이 복잡

### Vercel (비추)
- 무료 플랜이 개인/취미 전용, 다중 사용자 서비스 운영 시 약관 위반

## 3. 최종 추천: Cloudflare Pages

## 4. 보안 체크리스트
- 파일 업로드: xlsx만 허용, 3중 검증, 매크로 차단, 1MB 제한
- XSS: Flutter Text 위젯 기본 안전 + sanitization
- CSP: index.html에 Content-Security-Policy 메타 태그
- 파일은 서버에 저장하지 않고 클라이언트 사이드에서만 처리
