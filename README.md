# Datathon 2026

This repo combines two tracks of work for the competition:


Repo này kết hợp hai hướng phát triển chính cho cuộc thi:

- Pipeline dự báo tạo ra file nộp kết quả `Revenue` và `COGS` cho 548 ngày mục tiêu
- Bộ notebook EDA và storytelling giúp biến dữ liệu thương mại thô thành câu chuyện kinh doanh sẵn sàng trình bày

## What is in the repo


## Thư mục và nội dung chính

- `data/raw/`: dữ liệu gốc từ BTC
- `data/processed/`: dữ liệu đã xử lý, biến đổi
- `notebooks/`: các notebook EDA, baseline, storytelling
- `src/`: mã huấn luyện dự báo và chẩn đoán
- `tests/`: unit test cho các tiện ích dự báo
- `reports/`: lưu kết quả validation, chọn mô hình, chẩn đoán
- `submissions/`: các file CSV nộp kết quả

## Main files


## File quan trọng

- `notebooks/data_storytelling.ipynb`: notebook trình bày phân tích giá trị khách hàng, hiệu quả khuyến mãi, rủi ro hoàn trả
- `notebooks/eda_raw_data.ipynb`: khám phá dữ liệu thô
- `notebooks/eda_task_focused.ipynb`: EDA theo từng bài toán
- `src/two_pass_forecast.py`: script chính huấn luyện, đánh giá, chọn mô hình, xuất file nộp
- `src/analyze_forecast_failures.py`: chẩn đoán lỗi dự báo theo từng horizon

## Environment setup

Python 3.10+ is recommended.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install numpy pandas matplotlib seaborn scikit-learn lightgbm nbconvert nbclient jupyter-core pytest
```

## Thiết lập môi trường

Khuyến nghị dùng Python 3.10 trở lên.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install numpy pandas matplotlib seaborn scikit-learn lightgbm nbconvert nbclient jupyter-core pytest
```

## Run the storytelling notebook

From the repo root:

```bash
python -m nbconvert --to notebook --execute --inplace notebooks/data_storytelling.ipynb
```

## Chạy storytelling notebook

Từ thư mục gốc repo:

```bash
python -m nbconvert --to notebook --execute --inplace notebooks/data_storytelling.ipynb
```

The notebook is structured as a narrative rather than a loose EDA dump. It now answers three business questions:

1. Which customers drive the most value, and how concentrated is revenue?
2. Are promotions creating healthy demand, and which traffic sources convert most efficiently?
3. Which product categories and return reasons are creating the largest quality and refund risk?

Notebook này được thiết kế theo dạng kể chuyện (storytelling), trả lời ba câu hỏi kinh doanh:

1. Khách hàng nào mang lại giá trị lớn nhất, doanh thu tập trung ra sao?
2. Khuyến mãi có tạo ra nhu cầu lành mạnh không, nguồn traffic nào chuyển đổi tốt nhất?
3. Danh mục sản phẩm và lý do hoàn trả nào gây rủi ro chất lượng và hoàn tiền lớn nhất?

The notebook writes charts and printed takeaways back into the same `.ipynb` file.

## Run the forecasting pipeline

```bash
python src/two_pass_forecast.py --data-dir data/raw --out-dir submissions --report-dir reports
```

## Chạy pipeline dự báo

```bash
python src/two_pass_forecast.py --data-dir data/raw --out-dir submissions --report-dir reports
```

Key outputs:


Kết quả chính:

- `submissions/submission_pass1.csv`
- `submissions/submission_pass2.csv`
- `reports/forecasting/selection/selected_models.csv`
- `reports/forecasting/validation/model_tuning_summary.csv`
- `reports/forecasting/validation/model_holdout_summary.csv`

## Run diagnostics

```bash
python src/analyze_forecast_failures.py
```

## Chạy chẩn đoán lỗi dự báo

```bash
python src/analyze_forecast_failures.py
```

This writes error diagnostics to `reports/forecasting/diagnostics/`.

Kết quả sẽ được ghi vào `reports/forecasting/diagnostics/`.

## Run tests

```bash
pytest -q
```

## Chạy kiểm thử (unit test)

```bash
pytest -q
```

## Notes


## Ghi chú

- Pipeline dự báo mặc định dùng horizon 548 ngày.
- Có thể tận dụng các file validation lưu sẵn trong `reports/` để so sánh mô hình mà không cần huấn luyện lại ngay.
- `data_storytelling.ipynb` thân thiện trình bày, dùng đúng schema dữ liệu thực tế, không giả định cột hoặc join placeholder.
