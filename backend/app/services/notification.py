"""FCM 알림 서비스"""
import logging

logger = logging.getLogger(__name__)


async def send_push(tokens: list[str], title: str, body: str) -> tuple[int, int]:
    """FCM 푸시 알림 발송. (success_count, fail_count) 반환.

    firebase-admin이 설정되지 않은 경우 로그만 남기고 스킵.
    """
    if not tokens:
        return 0, 0

    try:
        import firebase_admin
        from firebase_admin import messaging

        if not firebase_admin._apps:
            logger.warning("Firebase 미초기화 — 알림 스킵")
            return 0, len(tokens)

        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            tokens=tokens,
        )
        response = messaging.send_each_for_multicast(message)
        return response.success_count, response.failure_count
    except ImportError:
        logger.warning("firebase-admin 미설치 — 알림 스킵")
        return 0, len(tokens)
    except Exception as e:
        logger.error(f"FCM 발송 실패: {e}")
        return 0, len(tokens)
