from pathlib import Path

path = Path("e:/Temp/datathon_2026/pitch_plan/pitch_plan.md")
if path.exists():
    content = path.read_text(encoding='utf-8')
    
    # 1. Update Methodology Section
    old_methodology_returns = """### Trục 4: Loại bỏ nhiễu trực quan (Visualization)
*   Sửa lỗi `FutureWarning` của Seaborn v0.14 bằng cách định nghĩa chính xác tham số `hue` trong các biểu đồ barplot.
*   Thay thế biểu đồ line chart chồng chéo 4 nguồn traffic bằng cấu trúc **FacetGrid** theo chiều dọc, hiển thị rõ ràng Conversion Rate (`orders per 1,000 sessions`) kèm dải **95% Confidence Interval (CI)** để loại bỏ dao động ngẫu nhiên."""

    new_methodology_returns = """### Trục 4: Loại bỏ nhiễu trực quan (Visualization)
*   Sửa lỗi `FutureWarning` của Seaborn v0.14 bằng cách định nghĩa chính xác tham số `hue` trong các biểu đồ barplot.
*   Thay thế biểu đồ line chart chồng chéo 4 nguồn traffic bằng cấu trúc **FacetGrid** theo chiều dọc, hiển thị rõ ràng Conversion Rate (`orders per 1,000 sessions`) kèm dải **95% Confidence Interval (CI)** để loại bỏ dao động ngẫu nhiên.

### Trục 5: Phát hiện Simpson's Paradox & Bác bỏ ý nghĩa thống kê của Returns
*   **Simpson's Paradox ở Category:** Tổng số tiền hoàn trả của Streetwear cực lớn ($406.7M, chiếm 80% hệ thống) dễ gây lầm tưởng chất lượng của nó kém nhất. Nhưng thực tế, tỷ lệ hoàn trả của Streetwear chỉ là **3.38%**, tương đương các danh mục khác như Outdoor (3.45%), Casual (3.26%) và thấp hơn GenZ (3.52%). Thất thoát lớn thuần túy do quy mô doanh thu khổng lồ của Streetwear ($13.1B).
*   **Bác bỏ Churn Correlation ở cấp đơn lẻ:** Sự khác biệt 0.3% (47.7% vs 47.4%) ở cấp đơn hàng có hoàn trả có **p-value = 0.31** (kiểm định Chi-Square), không có ý nghĩa thống kê. Sự cố hoàn trả đơn lẻ chưa trực tiếp dẫn tới ngưng hoạt động lâu dài."""

    content = content.replace(old_methodology_returns, new_methodology_returns)
    
    # 2. Update Slide 4 talk track
    old_slide4_talk = """### Slide 4: Chương 3 — Rò rỉ hoàn trả & Tác động đến rủi ro Churn
*   **Nội dung trình bày:** Tác động của Returns đến Churn Risk và top danh mục hoàn trả lớn nhất.
*   **Kịch bản nói (Talk Track):**
    > *"Cuối cùng, chương 3 làm rõ mối quan hệ giữa chất lượng vận hành sản phẩm và rủi ro mất khách. Dữ liệu cho thấy tổng thiệt hại do hoàn tiền đạt tới 510.6 triệu USD, tương đương 3.3% tổng doanh thu Net của chúng ta. Khi kiểm tra tác động của việc hoàn trả lên Churn Risk, khách hàng có đơn hoàn trả có tỷ lệ Churn Risk cao hơn một cách có ý nghĩa thống kê so với khách không gặp sự cố đổi trả (85.8% so với 85.4%). p-value của kiểm định này nhỏ hơn 0.01 do cỡ mẫu của chúng ta rất lớn.
    > 
    > Khi khoanh vùng thiệt hại, danh mục Streetwear đóng góp tới 406.7 triệu USD tiền hoàn trả, chiếm gần 80% tổng tổn thất của toàn hệ thống. Điều này chứng minh chất lượng sản phẩm hoặc khâu mô tả size của Streetwear đang gặp vấn đề nghiêm trọng. Giảm tỷ lệ hoàn trả của Streetwear không chỉ trực tiếp tiết kiệm chi phí hoàn tiền mà còn gián tiếp giảm tỷ lệ Churn của khách hàng."*"""

    new_slide4_talk = """### Slide 4: Chương 3 — Rò rỉ hoàn trả & Tác động đến rủi ro Ngưng Hoạt Động (ở cấp độ đơn hàng)
*   **Nội dung trình bày:** Tác động của Returns đến tỷ lệ đơn hàng ngưng hoạt động và phân tích rò rỉ theo Category.
*   **Kịch bản nói (Talk Track):**
    > *"Cuối cùng, chương 3 làm rõ mối quan hệ giữa chất lượng vận hành sản phẩm và tỷ lệ khách hàng ngưng hoạt động. Dữ liệu cho thấy tổng thiệt hại do hoàn tiền đạt tới 510.6 triệu USD, tương đương 3.3% tổng doanh thu Net của chúng ta.
    >
    > Khi kiểm tra mối tương quan ở cấp đơn hàng, đơn có hoàn trả có tỷ lệ thuộc nhóm khách ngưng hoạt động là 47.7%, so với 47.4% ở nhóm không hoàn trả. Sự khác biệt 0.3% này hoàn toàn **không có ý nghĩa thống kê với p-value = 0.31** từ kiểm định Chi-Square. Đây là điểm phản biện quan trọng: một sự cố hoàn trả đơn lẻ chưa đủ tác động để khách rời bỏ dịch vụ lâu dài.
    > 
    > Về mặt danh mục sản phẩm, Streetwear đóng góp tới 406.7 triệu USD tiền hoàn trả (gần 80% hệ thống). Tuy nhiên, đây là biểu hiện của **Simpson's Paradox & Thiên lệch Quy mô**. Tỷ lệ hoàn trả thực tế của Streetwear chỉ là **3.38%**, tương đương Casual (3.26%) và thấp hơn GenZ (3.52%). Vì vậy, Streetwear không có lỗi chất lượng vượt trội. Nhưng do quy mô doanh thu quá lớn, chỉ cần giảm nhẹ 0.2% tỷ lệ hoàn trả của Streetwear bằng việc cải tiến size chart sẽ mang lại khoản tiết kiệm ròng hơn 25 triệu USD cho doanh nghiệp."*"""

    content = content.replace(old_slide4_talk, new_slide4_talk)
    
    # 3. Update Slide 5 talk track
    content = content.replace("siết chặt chất lượng sản phẩm và mô tả size của dòng Streetwear để giảm khoản thiệt hại 406 triệu USD refund.",
                              "tập trung cải tiến nhẹ mô tả size chart dòng Streetwear để giảm 0.2% tỷ lệ hoàn trả, giúp tiết kiệm hơn 25 triệu USD (do quy mô doanh thu lớn).")

    path.write_text(content, encoding='utf-8')
    print("pitch_plan.md refined successfully!")
else:
    print("pitch_plan.md not found!")
