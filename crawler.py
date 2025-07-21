import pandas as pd
import os
import time
import re

from paddleocr import PaddleOCR
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
# TimeoutException을 명시적으로 처리하기 위해 추가
from selenium.common.exceptions import TimeoutException

# --- 크롤링 대상 사이트 정보 ---
INDEX_PAGE_URL = "https://www.yoonelecbook.com/161866d9-48f2-4ed9-a19d-d9ca212625e0"
CLICKABLE_CELLS_SELECTOR = "td.css-1yicpv2"
DETAIL_IMAGE_SELECTOR = "img.css-l68de9.e5kxa4l0"

# --- 함수 정의 (변경 없음) ---
def extract_text_via_temp_file(ocr_model, image_bytes: bytes) -> str:
    temp_image_path = "temp_ocr_image.png"
    try:
        with open(temp_image_path, "wb") as f:
            f.write(image_bytes)
        result = ocr_model.predict(temp_image_path)
        if result and result[0]:
            text_lines = [line[1][0] for line in result[0]]
            return "\n".join(text_lines)
        return ""
    finally:
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)

def parse_manual_text(raw_text: str) -> dict:
    if not raw_text:
        return {'manual_flag': '추출 실패', 'manual_col': '추출 실패', 'manual_html': '<h4>OCR 결과 없음</h4>'}
    try:
        flag_match = re.search(r'검출\s*FLAG\s*:\s*([0-9A-Z/]+)', raw_text)
        col_match = re.search(r'관련도면\s*:\s*([A-Z0-9\.]+)', raw_text)
        phenomenon_match = re.search(r'<현상>(.*?)<참조 도면>', raw_text, re.DOTALL)
        ref_drawing_match = re.search(r'<참조 도면>(.*?)<원인 및 조치사항>', raw_text, re.DOTALL)
        action_match = re.search(r'<원인 및 조치사항>(.*)', raw_text, re.DOTALL)
        manual_flag = flag_match.group(1).strip() if flag_match else "추출 실패"
        manual_col = col_match.group(1).strip() if col_match else "추출 실패"
        html_parts = []
        if phenomenon_match:
            content = phenomenon_match.group(1).strip().replace('\n', ' ')
            html_parts.append(f"<h4><현상></h4><p>{content}</p>")
        if ref_drawing_match:
            content = ref_drawing_match.group(1).strip().replace('\n', ' ')
            html_parts.append(f"<h4><참조 도면></h4><p>{content}</p>")
        if action_match:
            html_parts.append("<h4><원인 및 조치사항></h4>")
            items = [line.strip() for line in action_match.group(1).strip().split('\n') if line.strip()]
            if items:
                html_parts.append("<ol>")
                for item in items:
                    html_parts.append(f"<li>{item}</li>")
                html_parts.append("</ol>")
        manual_html = "".join(html_parts) if html_parts else "<h4>내용 추출 실패</h4>"
        return {'manual_flag': manual_flag, 'manual_col': manual_col, 'manual_html': manual_html}
    except Exception as e:
        return {'manual_flag': '파싱 오류', 'manual_col': '파싱 오류', 'manual_html': f'<h4>오류 발생: {e}</h4>'}

def save_results_to_excel(df: pd.DataFrame, filename: str):
    if df.empty: return
    df.to_excel(filename, index=False, engine='openpyxl')
    print(f"\n✅ 전체 결과가 엑셀 파일로 저장되었습니다: {os.path.abspath(filename)}")


# ===================================================================
# 메인 실행 로직 (대기 시간 및 예외 처리 강화)
# ===================================================================
def main():
    print("PaddleOCR 모델을 로딩합니다... (CPU 모드)")
    try:
        ocr_model = PaddleOCR(lang='korean')
        print("PaddleOCR 모델 로딩 완료.\n")
    except Exception as e:
        print(f"치명적 오류: PaddleOCR 모델 로딩에 실패했습니다. {e}")
        return

    print("웹 드라이버를 설정합니다...")
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # ★★★ 핵심 변경 사항 1: 대기 시간을 20초로 늘립니다 ★★★
    wait = WebDriverWait(driver, 20) 
    all_records = []
    
    try:
        print(f"메인 페이지로 이동: {INDEX_PAGE_URL}")
        driver.get(INDEX_PAGE_URL)
        
        num_cells = len(wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, CLICKABLE_CELLS_SELECTOR))))
        print(f"총 {num_cells}개의 항목을 발견했습니다. 순차적으로 처리합니다.")
        
        for i in range(num_cells):
            # 루프가 시작될 때마다 요소를 새로 찾습니다.
            cells = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, CLICKABLE_CELLS_SELECTOR)))
            cell_to_click = cells[i]
            
            # 메인 페이지 정보는 클릭하기 전에 미리 추출합니다.
            row = cell_to_click.find_element(By.XPATH, './ancestor::tr')
            columns = row.find_elements(By.TAG_NAME, 'td')
            main_category = columns[0].text.strip()
            sub_info = columns[1].text.strip().split()
            sub_index = sub_info[0] if sub_info else ""
            error_code = sub_info[1] if len(sub_info) > 1 else ""
            description = cell_to_click.text.strip().replace('\n', ' ')
            
            print(f"\n--- 처리 중 ({i+1}/{num_cells}): {main_category}-{error_code} ---")
            
            # 데이터를 저장할 딕셔너리를 먼저 생성합니다.
            current_record = {'대분류': main_category, '소분류': sub_index, '에러코드': error_code, '에러내용': description}

            # 이제 클릭합니다.
            driver.execute_script("arguments[0].scrollIntoView(true);", cell_to_click)
            time.sleep(0.2) # 스크롤 후 렌더링을 위한 아주 짧은 대기
            cell_to_click.click()

            # ★★★ 핵심 변경 사항 2: 상세 페이지 처리를 위한 전용 try-except 블록 ★★★
            try:
                # 이미지가 "화면에 보일 때까지" 최대 20초간 지능적으로 기다립니다.
                image_element = wait.until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, DETAIL_IMAGE_SELECTOR))
                )
                screenshot_bytes = image_element.screenshot_as_png
                
                raw_text = extract_text_via_temp_file(ocr_model, screenshot_bytes)
                print("  [성공] PaddleOCR로 매뉴얼 텍스트 추출 완료.")
                
                structured_data = parse_manual_text(raw_text)
                print("  [성공] 추출된 텍스트를 구조화된 데이터로 파싱 완료.")
                
                current_record.update(structured_data)

            except TimeoutException:
                # wait.until이 20초 내에 이미지를 찾지 못하면 이 블록이 실행됩니다.
                print("  [정보] 상세 페이지에 이미지가 없거나 시간 내에 로드되지 않았습니다.")
                no_manual_data = {'manual_flag': 'N/A', 'manual_col': 'N/A', 'manual_html': '<h4>관련 매뉴얼이 없습니다</h4>'}
                current_record.update(no_manual_data)

            all_records.append(current_record)
            driver.get(INDEX_PAGE_URL)
            
        if all_records:
            final_df = pd.DataFrame(all_records)
            final_df = final_df.reindex(columns=['대분류', '소분류', '에러코드', '에러내용', 'manual_flag', 'manual_col', 'manual_html'], fill_value="-")
            save_results_to_excel(final_df, 'error_manual_structured_final.xlsx')
        else:
            print("\n추출된 데이터가 없습니다.")
    except Exception as e:
        print(f"\n[치명적 오류] 크롤링 자동화 중 문제가 발생했습니다: {e}")
    finally:
        print("\n모든 작업 완료. 웹 드라이버를 종료합니다.")
        driver.quit()

if __name__ == "__main__":
    main()
