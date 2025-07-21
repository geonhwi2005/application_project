import os
import time
import re
import requests
import random

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

# --- 설정값 ---
INDEX_PAGE_URL = "https://www.yoonelecbook.com/9b5dae12-844f-4f60-b031-ec7786620da7"
DOWNLOAD_PATH = r"D:\Download\CODE\flutter\STVF_7" 

# --- 셀렉터 ---
CLICKABLE_CELLS_SELECTOR = "a.notion-link-token.notion-enable-hover"
DETAIL_IMAGE_SELECTOR = "img.css-l68de9.e5kxa4l0"
# ★ 상세 페이지의 에러 코드를 담고 있는 h1 태그
DETAIL_ERROR_CODE_SELECTOR = "h1.page-title" 

def main():
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)

    print("웹 드라이버를 설정합니다...")
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    options.add_argument('--log-level=3')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    wait = WebDriverWait(driver, 20)
    
    try:
        print(f"메인 페이지로 이동: {INDEX_PAGE_URL}")
        driver.get(INDEX_PAGE_URL)
        time.sleep(5)
        
        cells = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, CLICKABLE_CELLS_SELECTOR)))
        num_cells = len(cells)
        print(f"총 {num_cells}개의 항목을 발견했습니다. 다운로드를 시작합니다.")
        
        for i in range(num_cells):
            # 변수 초기화
            base_filename = f"temp_filename_{i+1}"
            
            try:
                # --- 1. 루프 시작 시 항상 메인 페이지에서 요소 새로고침 ---
                if driver.current_url != INDEX_PAGE_URL:
                    driver.get(INDEX_PAGE_URL)
                    time.sleep(3)

                cells = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, CLICKABLE_CELLS_SELECTOR)))
                cell_to_click = cells[i]

                # --- 2. 메인 페이지에서 '대분류'와 '설명' 미리 가져오기 ---
                row = cell_to_click.find_element(By.XPATH, './ancestor::tr')
                columns = row.find_elements(By.TAG_NAME, 'td')
                main_category = columns[0].text.strip() if len(columns) > 0 else "분류없음"
                description = cell_to_click.text.strip().replace('\n', ' ')

                # --- 3. 클릭해서 상세 페이지로 이동 ---
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cell_to_click)
                wait.until(EC.element_to_be_clickable(cell_to_click)).click()
                
                # --- 4. 상세 페이지에서 '에러 코드(h1)' 가져와서 최종 파일명 생성 ---
                try:
                    # h1 태그가 나타날 때까지 기다림
                    error_code_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, DETAIL_ERROR_CODE_SELECTOR)))
                    # h1 태그의 텍스트(예: F11)를 가져옴
                    error_code = error_code_element.text.strip()

                    # 파일명 조합
                    clean_description = re.sub(r'[\\/*?:"<>|]', "", description).strip()
                    if not clean_description: clean_description = "내용없음"
                    base_filename = f"{error_code}_{main_category}_{clean_description}"

                except Exception as e:
                    print(f"  [경고] 상세 페이지에서 에러코드(h1)를 찾지 못함({e}). 임시 파일명 사용.")
                    # 에러코드 못찾으면 그냥 메인페이지 정보로만 만듦
                    base_filename = f"NOCODE_{main_category}_{description}"

                print(f"\n--- 처리 중 ({i+1}/{num_cells}): {base_filename} ---")

                # --- 5. 다운로드 전 파일 존재 여부 확인 ---
                png_path = os.path.join(DOWNLOAD_PATH, base_filename + ".png")
                txt_path = os.path.join(DOWNLOAD_PATH, base_filename + ".txt")

                if os.path.exists(png_path) or os.path.exists(txt_path):
                    print(f"  [건너뛰기] 이미 처리된 항목입니다.")
                else:
                    # --- 6. 이미지 다운로드 또는 .txt 생성 ---
                    try:
                        # 이미지가 있으면 .png로 저장
                        image_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, DETAIL_IMAGE_SELECTOR)))
                        image_url = image_element.get_attribute('src')
                        response = requests.get(image_url, timeout=10)
                        response.raise_for_status()
                        with open(png_path, 'wb') as f:
                            f.write(response.content)
                        print(f"  [성공] 이미지를 저장했습니다: {png_path}")
                    except TimeoutException:
                        # 이미지가 없으면 .txt로 저장
                        print("  [정보] 이미지가 없습니다. 빈 .txt 파일을 생성합니다.")
                        with open(txt_path, 'w') as f:
                            pass
                        print(f"  [성공] 빈 파일을 저장했습니다: {txt_path}")

            except Exception as e:
                print(f"  [치명적 오류] {i+1}번째 항목 처리 실패({type(e).__name__}: {e}). 다음 항목으로 넘어갑니다.")
            finally:
                # 루프의 마지막에 항상 메인 페이지로 돌아가고, 잠시 대기
                if driver.current_url != INDEX_PAGE_URL:
                    driver.get(INDEX_PAGE_URL)
                
                sleep_time = random.uniform(1.5, 3.5)
                print(f"  봇 탐지 회피를 위해 {sleep_time:.2f}초 대기...")
                time.sleep(sleep_time)  

    except Exception as e:
        print(f"\n[치명적 오류] 자동화 중 문제가 발생했습니다: {type(e).__name__} - {e}")
    finally:
        print("\n모든 작업 완료. 웹 드라이버를 종료합니다.")
        driver.quit()
        
if __name__ == "__main__":
    main()
