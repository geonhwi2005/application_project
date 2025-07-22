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
# 링크가 포함된 '셀(td)'을 찾는 것이 핵심
CELLS_WITH_LINK_SELECTOR = "td:has(a.notion-link-token)"
# 셀 내부에서 링크를 찾기 위한 셀렉터
CLICKABLE_LINK_IN_CELL_SELECTOR = "a.notion-link-token.notion-enable-hover"
DETAIL_IMAGE_SELECTOR = "img.css-l68de9.e5kxa4l0"
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
        
        # 1. 링크를 포함하는 '모든 셀(td)'을 가져옵니다.
        cells = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, CELLS_WITH_LINK_SELECTOR)))
        num_cells = len(cells)
        print(f"총 {num_cells}개의 처리할 셀을 발견했습니다. 다운로드를 시작합니다.")
        
        for i in range(num_cells):
            base_filename = f"temp_filename_{i+1}"
            
            try:
                if driver.current_url != INDEX_PAGE_URL:
                    driver.get(INDEX_PAGE_URL)
                    time.sleep(3)

                # 매 루프마다 '셀' 목록을 새로고침합니다.
                cells = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, CELLS_WITH_LINK_SELECTOR)))
                current_cell = cells[i]

                # 2. 현재 셀이 속한 행(tr)을 찾아 '대분류(F1, F2...)'를 가져옵니다.
                row = current_cell.find_element(By.XPATH, './ancestor::tr')
                row_category = row.find_elements(By.TAG_NAME, 'td')[0].text.strip() if row else "분류없음"

                # 3. ★★★ 핵심 로직 ★★★
                #    현재 '셀' 안에 있는 모든 링크를 찾습니다.
                links_in_cell = current_cell.find_elements(By.CSS_SELECTOR, CLICKABLE_LINK_IN_CELL_SELECTOR)
                
                # 가장 긴 텍스트를 가진 링크를 '대표 링크'로 선택합니다.
                # 이렇게 하면 "정지 중..."과 "▲" 중에서 "정지 중..."이 선택됩니다.
                if not links_in_cell:
                    print(f"  [건너뛰기] {i+1}번째 셀에서 링크를 찾지 못했습니다.")
                    continue
                
                main_link = max(links_in_cell, key=lambda link: len(link.text.strip()))
                
                description = main_link.text.strip().replace('\n', ' ')
                
                # 4. 대표 링크를 클릭하여 상세 페이지로 이동합니다.
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", main_link)
                wait.until(EC.element_to_be_clickable(main_link)).click()
                
                # 5. 상세 페이지에서 에러 코드를 가져와 최종 파일명을 만듭니다.
                try:
                    error_code_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, DETAIL_ERROR_CODE_SELECTOR)))
                    error_code = error_code_element.text.strip()

                    clean_description = re.sub(r'[\\/*?:"<>|]', "", description).strip()
                    if not clean_description: clean_description = "내용없음"
                    
                    # 최종 파일명 조합
                    base_filename = f"{error_code}_{row_category}_{clean_description}"

                except Exception as e:
                    print(f"  [경고] 상세 페이지에서 에러코드(h1)를 찾지 못함({e}). 임시 파일명 사용.")
                    clean_description = re.sub(r'[\\/*?:"<>|]', "", description).strip()
                    base_filename = f"NOCODE_{row_category}_{clean_description}"

                print(f"\n--- 처리 중 ({i+1}/{num_cells}): {base_filename} ---")

                # --- 이후 다운로드 로직은 동일 ---
                png_path = os.path.join(DOWNLOAD_PATH, base_filename + ".png")
                txt_path = os.path.join(DOWNLOAD_PATH, base_filename + ".txt")

                if os.path.exists(png_path) or os.path.exists(txt_path):
                    print(f"  [건너뛰기] 이미 처리된 항목입니다.")
                    continue
                
                try:
                    image_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, DETAIL_IMAGE_SELECTOR)))
                    image_url = image_element.get_attribute('src')
                    response = requests.get(image_url, timeout=10)
                    response.raise_for_status()
                    with open(png_path, 'wb') as f:
                        f.write(response.content)
                    print(f"  [성공] 이미지를 저장했습니다: {png_path}")
                except TimeoutException:
                    print("  [정보] 이미지가 없습니다. 빈 .txt 파일을 생성합니다.")
                    with open(txt_path, 'w') as f:
                        pass
                    print(f"  [성공] 빈 파일을 저장했습니다: {txt_path}")

            except Exception as e:
                print(f"  [치명적 오류] {i+1}번째 셀 처리 실패({type(e).__name__}: {e}). 다음 항목으로 넘어갑니다.")
            finally:
                if driver.current_url != INDEX_PAGE_URL:
                    driver.back()
                
                sleep_time = random.uniform(1.5, 3.5)
                time.sleep(sleep_time)

    except Exception as e:
        print(f"\n[치명적 오류] 자동화 중 문제가 발생했습니다: {type(e).__name__} - {e}")
    finally:
        print("\n모든 작업 완료. 웹 드라이버를 종료합니다.")
        driver.quit()
        
if __name__ == "__main__":
    main()
