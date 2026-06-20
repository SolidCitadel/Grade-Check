"""
경희대학교 성적 확인 알림 봇 (Playwright / long-lived 세션)

2차 인증(OTP APP 푸시 승인)이 매 로그인마다 필요하고, 인증 세션이 모두
세션 쿠키(JSESSIONID)라 브라우저를 닫으면 소멸한다. 따라서:
  - 브라우저를 프로세스 생존 동안 계속 살려둔다(long-lived).
  - 주기적 성적 페이지 접근이 keep-alive(서버 유휴 만료 리셋) 겸 변동 감지다.
  - 세션 만료(로그인 페이지로 튕김) 시 자동 재로그인하지 않고 Discord로 알린 뒤
    부트스트랩 로그인(폰 승인 1회)을 재수행한다.
"""
import os
import time
import json
from datetime import datetime
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv()


def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class GradeChecker:
    def __init__(self):
        self.login_url = os.getenv("LOGIN_URL")
        self.grade_url = os.getenv("GRADE_URL")
        self.username = os.getenv("PORTAL_ID")
        self.password = os.getenv("PASSWORD")
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        self.headless = os.getenv("HEADLESS", "true").lower() != "false"
        self.login_wait_sec = int(os.getenv("LOGIN_WAIT_SEC", "300"))

        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        self.history_file = os.path.join(self.data_dir, "grades_history.json")
        self.profile_dir = os.path.join(self.data_dir, "pw-profile")

        self._pw = None
        self.ctx = None
        self.page = None

    # ------------------------------------------------------------------ #
    # 브라우저 수명 관리
    # ------------------------------------------------------------------ #
    def start_browser(self):
        self._pw = sync_playwright().start()
        self.ctx = self._pw.chromium.launch_persistent_context(
            self.profile_dir,
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--window-size=1280,950"],
            viewport={"width": 1280, "height": 900},
        )
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        # 2차인증 발송 시 뜨는 네이티브 alert 자동 확인
        self.page.on("dialog", lambda d: d.accept())
        self.page.set_default_timeout(15000)

    def stop_browser(self):
        try:
            if self.ctx:
                self.ctx.close()
        finally:
            if self._pw:
                self._pw.stop()

    # ------------------------------------------------------------------ #
    # Discord 알림
    # ------------------------------------------------------------------ #
    def send_discord_notification(self, message, embed=None):
        if not self.webhook_url:
            print("⚠️ Discord Webhook URL 미설정 — 알림 생략")
            return
        try:
            data = {"content": message}
            if embed:
                data["embeds"] = [embed]
            r = requests.post(self.webhook_url, json=data, timeout=10)
            ok = r.status_code == 204
            print(f"[{ts()}] Discord 알림 {'성공' if ok else f'실패({r.status_code})'}")
        except Exception as e:
            print(f"[{ts()}] 알림 전송 오류: {e}")

    # ------------------------------------------------------------------ #
    # 로그인 상태 판별
    # ------------------------------------------------------------------ #
    def _on_login_page(self):
        url = (self.page.url or "").lower()
        if "loginctr/login" in url or "login.do" in url:
            return True
        return self.page.locator("#userId").count() > 0

    # ------------------------------------------------------------------ #
    # 부트스트랩 로그인 (반자동: 봇이 끌고, 폰 승인은 사용자가)
    # ------------------------------------------------------------------ #
    def login(self):
        print(f"[{ts()}] 로그인 시도")
        try:
            self.page.goto(self.login_url, wait_until="domcontentloaded")
            self.page.wait_for_selector("#userId", timeout=15000)
            self.page.keyboard.press("Escape")  # 공지 팝업 있으면 닫기(없어도 무해)

            self.page.fill("#userId", self.username)
            self.page.fill("#userPw", self.password)
            self.page.locator("button.btn_login:visible", has_text="로그인").first.click()

            # 2차인증 다이얼로그(인증방법 select) 대기
            self.page.locator("select:visible").first.wait_for(state="visible", timeout=15000)
            self.page.locator("select:visible").first.select_option(label="OTP APP")
            time.sleep(0.5)
            self.page.locator("button:visible", has_text="Push 발송").first.click()

            self.send_discord_notification(
                "📲 **2차 인증 필요** — 경희대 OTP앱(KHU-OTP) 알림에서 **승인**을 눌러주세요.")
            print(f"[{ts()}] 📲 폰 승인 대기 (최대 {self.login_wait_sec}초)")

            deadline = time.time() + self.login_wait_sec
            first = True
            while time.time() < deadline:
                time.sleep(14 if first else 8)
                first = False
                try:
                    self.page.locator(".ui-dialog:visible").locator(
                        "button:has-text('로그인')").first.click(timeout=3000)
                except Exception:
                    pass  # 다이얼로그가 이미 닫혔거나(승인 완료 직후) 미출현
                time.sleep(2.5)
                url = (self.page.url or "").lower()
                if "portal.khu.ac.kr" in url and "login" not in url:
                    print(f"[{ts()}] ✅ 로그인 성공")
                    self.send_discord_notification("✅ 로그인 완료 — 성적 모니터링을 재개합니다.")
                    return True

            print(f"[{ts()}] ❌ 로그인 시간 초과")
            self.send_discord_notification("⚠️ 재로그인 시간 초과 — 다음 주기에 다시 시도합니다.")
            return False
        except Exception as e:
            print(f"[{ts()}] 로그인 실패: {e}")
            self._save_screenshot("login_error.png")
            self.send_discord_notification(f"⚠️ 로그인 중 오류: {str(e)[:300]}")
            return False

    # ------------------------------------------------------------------ #
    # 성적 확인
    # ------------------------------------------------------------------ #
    def check_grades(self):
        """성적 페이지 접근 → 만료면 'EXPIRED', 정상 파싱이면 'OK', 오류면 'ERROR'."""
        try:
            self.page.goto(self.grade_url, wait_until="domcontentloaded")
            time.sleep(1)
            if self._on_login_page():
                print(f"[{ts()}] 세션 만료 감지(로그인 페이지로 리다이렉트)")
                return "EXPIRED"

            try:
                self.page.wait_for_selector("div#cont1 table.t_list", timeout=30000)
                time.sleep(1)
            except PWTimeout:
                print(f"[{ts()}] 성적 테이블 로딩 타임아웃")
                self._save_screenshot("grade_timeout.png")
                return "ERROR"

            rows = self.page.locator("div#cont1 table.t_list tbody tr")
            n = rows.count()
            print(f"[{ts()}] 발견된 행: {n}")

            current_grades = []
            for i in range(n):
                row = rows.nth(i)
                if row.locator("td[data-mb='교과목']").count() == 0:
                    continue  # 헤더 행 등 제외
                try:
                    subject = row.locator("td[data-mb='교과목']").first.inner_text().strip()
                    grade = row.locator("td[data-mb='등급']").first.inner_text().strip()
                    status = row.locator("td[data-mb='성적입력']").first.inner_text().strip()
                except Exception:
                    continue
                current_grades.append({"subject": subject, "grade": grade, "status": status})
                print(f"- {subject}: {grade} ({status})")

            print(f"[{ts()}] 유효 과목 {len(current_grades)}개")
            self.process_grade_updates(current_grades)
            return "OK"
        except Exception as e:
            print(f"[{ts()}] 성적 확인 실패: {e}")
            self._save_screenshot("grade_error.png")
            return "ERROR"

    def process_grade_updates(self, current_grades):
        if not os.path.exists(self.history_file):
            self.save_history(current_grades)
            print("첫 실행: 현재 상태 저장")
            self.send_discord_notification("👋 성적 알림 봇 시작 — 현재 성적 상태를 저장했습니다.")
            return

        with open(self.history_file, "r", encoding="utf-8") as f:
            previous_grades = json.load(f)
        prev_dict = {g["subject"]: g for g in previous_grades}

        updates = []
        for curr in current_grades:
            subject = curr["subject"]
            if subject in prev_dict:
                prev = prev_dict[subject]
                if prev["status"] != curr["status"] or prev["grade"] != curr["grade"]:
                    print(f"변동 감지: {subject} | {prev['status']}->{curr['status']} | "
                          f"{prev['grade']}->{curr['grade']}")
                    updates.append(curr)
            else:
                if curr["status"] != "미입력" and curr["grade"] != "-":
                    updates.append(curr)

        if updates:
            print(f"🎉 {len(updates)}개 업데이트 발견")
            embed = {
                "title": "🎉 성적 발표 알림",
                "description": "새로운 성적이 등록되었습니다!",
                "color": 5814783,
                "fields": [{"name": u["subject"],
                            "value": f"성적: **{u['grade']}**\n상태: {u['status']}",
                            "inline": False} for u in updates],
                "timestamp": datetime.utcnow().isoformat(),
            }
            self.send_discord_notification("새로운 성적이 확인되었습니다!", embed)
            self.save_history(current_grades)
        else:
            print("변동 없음")

    def save_history(self, grades):
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(grades, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"기록 저장 실패: {e}")

    def _save_screenshot(self, name):
        try:
            self.page.screenshot(path=name)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 메인 루프 (long-lived)
    # ------------------------------------------------------------------ #
    def run(self, interval_minutes=30):
        print(f"🎓 경희대 성적 확인 봇 시작 | 주기 {interval_minutes}분 | "
              f"headless={self.headless}")
        self.start_browser()
        self.send_discord_notification(
            f"🤖 봇이 시작되었습니다. {interval_minutes}분마다 성적을 확인합니다.")
        try:
            while True:
                status = self.check_grades()
                if status == "EXPIRED":
                    self.send_discord_notification("🔒 세션 만료 — 재로그인이 필요합니다.")
                    if self.login():
                        self.check_grades()  # 재로그인 직후 즉시 재확인
                time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            print("\n봇 종료")
        except Exception as e:
            print(f"치명적 오류: {e}")
            try:
                self.send_discord_notification(f"⚠️ **봇 오류**\n```{str(e)[:1800]}```")
            except Exception:
                pass
        finally:
            self.stop_browser()


def main():
    if not all([os.getenv("LOGIN_URL"), os.getenv("GRADE_URL"),
                os.getenv("PORTAL_ID"), os.getenv("PASSWORD")]):
        print("오류: .env 설정을 확인하세요 (LOGIN_URL/GRADE_URL/PORTAL_ID/PASSWORD).")
        return
    checker = GradeChecker()
    interval = int(os.getenv("CHECK_INTERVAL", "30"))
    checker.run(interval_minutes=interval)


if __name__ == "__main__":
    main()
