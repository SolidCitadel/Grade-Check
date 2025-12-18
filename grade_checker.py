import os
import time
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import schedule

# 환경변수 로드
load_dotenv()

class GradeChecker:
    def __init__(self, headless=True):
        """
        경희대학교 성적 확인 자동화 클래스
        """
        self.login_url = os.getenv('LOGIN_URL')
        self.grade_url = os.getenv('GRADE_URL')
        self.username = os.getenv('PORTAL_ID')
        self.password = os.getenv('PASSWORD')
        self.webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        self.headless = headless
        self.driver = None
        # 데이터 디렉토리 설정 (Docker 마운트 용)
        self.data_dir = 'data'
        os.makedirs(self.data_dir, exist_ok=True)
        self.history_file = os.path.join(self.data_dir, 'grades_history.json')

    def setup_driver(self):
        """웹드라이버 설정"""
        chrome_options = Options()

        if self.headless:
            chrome_options.add_argument('--headless')

        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        # 브라우저 창 크기 설정 (반응형 사이트 대응)
        chrome_options.add_argument('--window-size=1920,1080')

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.implicitly_wait(10)

    def send_discord_notification(self, message, embed=None):
        """Discord Webhook으로 알림 전송"""
        if not self.webhook_url:
            print("⚠️ Discord Webhook URL이 설정되지 않아 알림을 보낼 수 없습니다.")
            return

        try:
            data = {"content": message}
            if embed:
                data["embeds"] = [embed]
            
            response = requests.post(self.webhook_url, json=data)
            if response.status_code == 204:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Discord 알림 전송 성공")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Discord 알림 전송 실패: {response.status_code}")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 알림 전송 중 오류: {str(e)}")

    def login(self):
        """경희대학교 포털 로그인"""
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 로그인 시도 중...")
            self.driver.get(self.login_url)

            # Alert가 있다면 처리 (가끔 세션 만료 알림 등이 뜰 때 대비)
            try:
                alert = self.driver.switch_to.alert
                alert.accept()
            except:
                pass

            # ID 입력
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "userId"))
            )
            username_field.clear()
            time.sleep(0.5)
            username_field.send_keys(self.username)

            # PW 입력
            password_field = self.driver.find_element(By.ID, "userPw")
            password_field.clear()
            time.sleep(0.5)
            password_field.send_keys(self.password)
            time.sleep(0.5)

            # 로그인 버튼 클릭
            login_button = self.driver.find_element(By.CSS_SELECTOR, "button.loginbtn1")
            login_button.click()

            # 로그인 실패 Alert 확인 (비밀번호 틀림 등)
            try:
                WebDriverWait(self.driver, 3).until(EC.alert_is_present())
                alert = self.driver.switch_to.alert
                error_msg = alert.text
                print(f"⚠️ 로그인 경고 창 감지: {error_msg}")
                alert.accept()
                return False
            except:
                # Alert가 없으면 로그인 성공으로 간주하고 진행
                pass

            # 로그인 완료 및 리다이렉트 대기
            time.sleep(5)
            
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 로그인 성공")
            return True

        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 로그인 실패: {str(e)}")
            self.driver.save_screenshot('login_error.png')
            return False

    def check_grades(self):
        """성적 페이지 확인 및 '미입력' 상태 모니터링"""
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 성적 페이지 이동 중...")
            self.driver.get(self.grade_url)

            # 성적 테이블 로딩 대기 (최대 30초)
            try:
                print("성적 테이블 로딩 대기 중 (div#cont1 table.t_list)...")
                WebDriverWait(self.driver, 30).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "div#cont1 table.t_list"))
                )
                time.sleep(1) # 렌더링 안정화
            except Exception as e:
                print(f"테이블 로딩 대기 중 오류 또는 타임아웃: {str(e)}")
                # 타임아웃 시 소스 저장
                try:
                    with open("debug_page_source_timeout.html", "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                    print("디버그용 페이지 소스를 debug_page_source_timeout.html로 저장했습니다.")
                except:
                    pass

            # 성적 테이블 행 파싱 (구체적인 셀렉터 사용)
            grade_rows = self.driver.find_elements(By.CSS_SELECTOR, "div#cont1 table.t_list tbody tr")
            
            if not grade_rows:
                print("성적 테이블 행을 찾을 수 없습니다.")
                # 행을 못 찾았을 때도 소스 저장
                try:
                    with open("debug_page_source_not_found.html", "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                    print("디버그용 페이지 소스를 debug_page_source_not_found.html로 저장했습니다.")
                except:
                    pass
                return False

            current_grades = []
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 발견된 행 개수: {len(grade_rows)}")

            for row in grade_rows:
                try:
                    # 데이터 유효성 검증 (헤더 행 제외)
                    cells = row.find_elements(By.CSS_SELECTOR, "td[data-mb='교과목']")
                    if not cells:
                        continue

                    # 각 셀 데이터 추출
                    subject = cells[0].text.strip()
                    grade = row.find_element(By.CSS_SELECTOR, "td[data-mb='등급']").text.strip()
                    status = row.find_element(By.CSS_SELECTOR, "td[data-mb='성적입력']").text.strip()
                    
                    grade_info = {
                        "subject": subject,
                        "grade": grade,
                        "status": status
                    }
                    current_grades.append(grade_info)
                    
                    print(f"- {subject}: {grade} ({status})")

                except Exception as e:
                    # print(f"행 파싱 중 오류: {str(e)}")
                    continue

            print(f"[{datetime.now().strftime('%H:%M:%S')}] 총 {len(current_grades)}개 과목 유효 데이터 확인됨")

            # 변경사항 확인 및 알림 트리거
            self.process_grade_updates(current_grades)
            
            return True

        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 성적 확인 실패: {str(e)}")
            self.driver.save_screenshot('grade_check_error.png')
            return False

    def process_grade_updates(self, current_grades):
        """이전 성적과 비교하여 업데이트 확인"""
        if not os.path.exists(self.history_file):
            # 첫 실행 시 기록만 저장
            self.save_history(current_grades)
            print("첫 실행: 현재 상태를 저장했습니다.")
            self.send_discord_notification("👋 성적 알림 봇이 시작되었습니다.\n현재 성적 상태가 저장되었습니다.")
            return

        with open(self.history_file, 'r', encoding='utf-8') as f:
            previous_grades = json.load(f)

        # 딕셔너리로 변환하여 비교 용이하게 함 (Subject -> Info)
        prev_dict = {g['subject']: g for g in previous_grades}
        
        updates = []
        
        for curr in current_grades:
            subject = curr['subject']
            curr_status = curr['status']
            curr_grade = curr['grade']
            
            if subject in prev_dict:
                prev = prev_dict[subject]
                prev_status = prev['status']
                
                # 감지 조건:
                # 1. 상태가 변경된 경우 (예: '미입력' -> '입력')
                # 2. 등급이 변경된 경우 (예: '-' -> 'A+', 또는 'A' -> 'A+')
                status_changed = (prev_status != curr_status)
                grade_changed = (prev['grade'] != curr_grade)
                
                if status_changed or grade_changed:
                    # 변경 사항이 있으면 업데이트 목록에 추가하되,
                    # 단순 순서 변경 등이 아닌 실제 의미있는 변화인지 로깅
                    print(f"변동 감지: {subject} | 상태: {prev_status}->{curr_status} | 등급: {prev['grade']}->{curr_grade}")
                    updates.append(curr)
            else:
                # 새로운 과목 발견 (드문 케이스지만 처리)
                if curr['status'] != "미입력" and curr['grade'] != "-":
                    updates.append(curr)

        if updates:
            print(f"🎉 {len(updates)}개의 새로운 성적 업데이트 발견!")
            
            embed_fields = []
            for item in updates:
                embed_fields.append({
                    "name": item['subject'],
                    "value": f"성적: **{item['grade']}**\n상태: {item['status']}",
                    "inline": False
                })
                
            embed = {
                "title": "🎉 성적 발표 알림",
                "description": "새로운 성적이 등록되었습니다!",
                "color": 5814783,  # Green
                "fields": embed_fields,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.send_discord_notification("새로운 성적이 확인되었습니다!", embed)
            self.save_history(current_grades)
        else:
            print("변동 사항 없음")

    def save_history(self, grades):
        """성적 기록 저장"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(grades, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"기록 저장 실패: {str(e)}")

    def run_check(self):
        """한 번의 확인 사이클 실행"""
        try:
            self.setup_driver()
            if self.login():
                self.check_grades()
        except Exception as e:
            print(f"실행 중 오류: {str(e)}")
        finally:
            if self.driver:
                self.driver.quit()

    def run_scheduled(self, interval_minutes=30):
        """주기적으로 성적 확인"""
        print(f"🎓 경희대학교 성적 확인 봇 가동 시작")
        print(f"⏱️ 확인 주기: {interval_minutes}분")
        print(f"종료하려면 Ctrl+C를 누르세요.\n")

        # 시작 시 알림
        self.send_discord_notification(f"🤖 봇이 시작되었습니다. {interval_minutes}분마다 성적을 확인합니다.")

        # 즉시 한 번 실행
        self.run_check()

        schedule.every(interval_minutes).minutes.do(self.run_check)

        while True:
            schedule.run_pending()
            time.sleep(1)

def main():
    if not all([os.getenv('LOGIN_URL'), os.getenv('PORTAL_ID'), os.getenv('PASSWORD')]):
        print("오류: .env 파일 설정을 확인해주세요.")
        return

    checker = GradeChecker(headless=True)
    
    # 환경변수에서 주기 읽기
    interval = int(os.getenv('CHECK_INTERVAL', 30))
    
    try:
        checker.run_scheduled(interval_minutes=interval)
    except KeyboardInterrupt:
        print("\n봇을 종료합니다.")

if __name__ == "__main__":
    main()
