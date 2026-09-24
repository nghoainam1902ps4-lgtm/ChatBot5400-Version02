# Nhà cung cấp AI — Hướng dẫn cấu hình

Hướng dẫn thiết lập đầy đủ cho từng nhà cung cấp AI thông qua **giao diện Cài đặt**.

> **Mới từ v1.2**: Mọi thông tin xác thực (credential) của nhà cung cấp AI hiện được quản lý qua giao diện Cài đặt. Việc dùng biến môi trường cho API key đã bị ngưng khuyến nghị.

---

## Cách thiết lập nhà cung cấp hoạt động

Open Notebook dùng **hệ thống dựa trên credential** để quản lý các nhà cung cấp AI:

1. **Lấy API key** từ website của nhà cung cấp
2. Mở **Quản lý** → **Mô hình** → **Thêm Credential**
3. **Kiểm tra kết nối** để xác minh hoạt động
4. **Khám phá & Đăng ký mô hình** để đưa chúng vào sử dụng
5. **Bắt đầu dùng** nhà cung cấp trong các notebook của bạn

> **Điều kiện tiên quyết**: Bạn phải đặt `OPEN_NOTEBOOK_ENCRYPTION_KEY` trước khi lưu credential (mã hóa dữ liệu nhạy cảm). Xem mục *Cấu hình API → Thiết lập mã hóa* để biết chi tiết.

---

## Nhà cung cấp đám mây (Khuyến nghị cho hầu hết người dùng)

### OpenAI

**Chi phí:** ~0,03–0,15 USD / 1K token (tùy mô hình)

**Lấy API Key:**
1. Truy cập https://platform.openai.com/api-keys
2. Tạo tài khoản (nếu cần)
3. Tạo API key mới (bắt đầu bằng "sk-proj-")
4. Nạp thêm ≥ 5 USD tín dụng vào tài khoản

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **OpenAI**
4. Đặt tên (ví dụ: "OpenAI của tôi")
5. Dán API key
6. Bấm **Lưu**, rồi **Kiểm tra kết nối**
7. Bấm **Khám phá mô hình** để tìm các mô hình khả dụng
8. Bấm **Đăng ký mô hình** để đưa vào sử dụng

**Mô hình khả dụng (trong Open Notebook):**
- `gpt-4o` — Chất lượng tốt nhất, nhanh (phiên bản mới nhất)
- `gpt-4o-mini` — Nhanh, rẻ, phù hợp để thử nghiệm
- `o1` — Mô hình suy luận nâng cao (chậm hơn, đắt hơn)
- `o1-mini` — Mô hình suy luận nhanh hơn

**Khuyến nghị:**
- Dùng chung: `gpt-4o` (cân bằng tốt nhất)
- Thử nghiệm/tiết kiệm: `gpt-4o-mini` (rẻ hơn 90%)
- Suy luận phức tạp: `o1` (tốt nhất cho bài toán khó)

**Ước tính chi phí:**
```
Dùng nhẹ:    1–5 USD/tháng
Dùng vừa:    10–30 USD/tháng
Dùng nhiều:  50–100+ USD/tháng
```

**Khắc phục sự cố:**
- "Invalid API key" → Kiểm tra key bắt đầu bằng "sk-proj-" và kiểm tra kết nối trong Quản lý → Mô hình
- "Rate limit exceeded" → Chờ hoặc nâng cấp tài khoản
- "Model not available" → Thử `gpt-4o-mini`, hoặc khám phá lại mô hình

---

### Anthropic (Claude)

**Chi phí:** ~0,80–3,00 USD / 1M token (rẻ hơn OpenAI với ngữ cảnh dài)

**Lấy API Key:**
1. Truy cập https://console.anthropic.com/
2. Tạo tài khoản hoặc đăng nhập
3. Vào mục API keys
4. Tạo API key mới (bắt đầu bằng "sk-ant-")

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **Anthropic**
4. Đặt tên, dán API key
5. Bấm **Lưu**, rồi **Kiểm tra kết nối**
6. Bấm **Khám phá mô hình** → **Đăng ký mô hình**

**Mô hình khả dụng:**
- `claude-sonnet-4-5-20250929` — Mới nhất, chất lượng tốt nhất (khuyến nghị)
- `claude-3-5-sonnet-20241022` — Thế hệ trước, vẫn rất tốt
- `claude-3-5-haiku-20241022` — Nhanh, rẻ
- `claude-opus-4-5-20251101` — Mạnh nhất, đắt

**Khuyến nghị:**
- Dùng chung: `claude-sonnet-4-5` (tổng thể tốt nhất, mới nhất)
- Tiết kiệm: `claude-3-5-haiku` (rẻ hơn 80%)
- Phức tạp: `claude-opus-4-5` (mạnh nhất)

**Ước tính chi phí:**
```
Sonnet: 3–20 USD/tháng (dùng điển hình)
Haiku:  0,50–3 USD/tháng
Opus:   10–50+ USD/tháng
```

**Ưu điểm:**
- Hỗ trợ ngữ cảnh dài rất tốt (200K token)
- Suy luận xuất sắc
- Xử lý nhanh

**Khắc phục sự cố:**
- "Invalid API key" → Kiểm tra key bắt đầu bằng "sk-ant-" và kiểm tra trong Quản lý → Mô hình
- "Overloaded" → Anthropic đang bận, thử lại sau
- "Model unavailable" → Khám phá lại mô hình từ credential

---

### Anthropic Compatible (Tương thích Anthropic)

Dùng nhà cung cấp này cho các dịch vụ triển khai Anthropic Messages API tại một URL tùy chỉnh.

1. Vào **Quản lý** → **Mô hình**
2. Thêm credential **Anthropic Compatible**
3. Nhập API key và base URL của dịch vụ (gốc API, có hoặc không có hậu tố `/v1`)
4. Lưu và kiểm tra kết nối
5. Khám phá mô hình, hoặc tìm và đăng ký thủ công một mô hình nếu endpoint không liệt kê

Credential kiểu Anthropic Compatible chỉ hỗ trợ mô hình ngôn ngữ.

---

### Google Gemini

**Chi phí:** ~0,075–0,30 USD / 1K token (cạnh tranh với OpenAI)

**Lấy API Key:**
1. Truy cập https://aistudio.google.com/app/apikey
2. Tạo tài khoản hoặc đăng nhập
3. Tạo API key mới

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **Google Gemini**
4. Đặt tên, dán API key
5. Bấm **Lưu**, rồi **Kiểm tra kết nối**
6. Bấm **Khám phá mô hình** → **Đăng ký mô hình**

**Mô hình khả dụng:**
- `gemini-2.5-pro` — Mạnh nhất, tốt cho ngữ cảnh dài (1M token)
- `gemini-3.5-flash` — Nhanh, phù hợp dùng chung
- `gemini-3.1-flash-lite` — Nhanh và rẻ nhất
- `gemini-2.5-flash` — Bản ổn định thế hệ trước, rẻ hơn

**Khuyến nghị:**
- Dùng chung: `gemini-3.5-flash` (đáng giá nhất, mới nhất)
- Tiết kiệm: `gemini-3.1-flash-lite` (rất rẻ)
- Phức tạp/ngữ cảnh dài: `gemini-2.5-pro` (ngữ cảnh 1M token)

**Ưu điểm:**
- Ngữ cảnh rất dài (1M token)
- Đa phương thức (ảnh, âm thanh, video)
- Tốt cho podcast

**Khắc phục sự cố:**
- "API key invalid" → Lấy key mới tại aistudio.google.com
- "Quota exceeded" → Gói miễn phí bị giới hạn, nâng cấp tài khoản
- "Model not found" → Khám phá lại mô hình từ credential

---

### Groq

**Chi phí:** ~0,05 USD / 1M token (rẻ nhất, nhưng ít mô hình)

**Lấy API Key:**
1. Truy cập https://console.groq.com/keys
2. Tạo tài khoản hoặc đăng nhập
3. Tạo API key mới

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **Groq**
4. Đặt tên, dán API key
5. Bấm **Lưu**, rồi **Kiểm tra kết nối**
6. Bấm **Khám phá mô hình** → **Đăng ký mô hình**

**Mô hình khả dụng:**
- `llama-3.3-70b-versatile` — Tốt nhất trên Groq (khuyến nghị)
- `llama-3.1-70b-versatile` — Nhanh, đủ năng lực
- `mixtral-8x7b-32768` — Lựa chọn thay thế tốt
- `gemma2-9b-it` — Nhỏ, rất nhanh

**Khuyến nghị:**
- Chất lượng: `llama-3.3-70b-versatile` (tổng thể tốt nhất)
- Tốc độ: `gemma2-9b-it` (siêu nhanh)
- Cân bằng: `llama-3.1-70b-versatile`

**Ưu điểm:**
- Suy luận cực nhanh
- Rất rẻ
- Tốt cho tác vụ biến đổi/xử lý hàng loạt

**Nhược điểm:**
- Ít mô hình
- Mô hình nhỏ hơn OpenAI/Anthropic

**Khắc phục sự cố:**
- "Rate limited" → Gói miễn phí có giới hạn, nâng cấp
- "Model not available" → Khám phá lại mô hình từ credential

---

### OpenRouter

**Chi phí:** Tùy mô hình (0,05–15 USD / 1M token)

**Lấy API Key:**
1. Truy cập https://openrouter.ai/keys
2. Tạo tài khoản hoặc đăng nhập
3. Nạp tín dụng vào tài khoản
4. Tạo API key mới

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **OpenRouter**
4. Đặt tên, dán API key
5. Bấm **Lưu**, rồi **Kiểm tra kết nối**
6. Bấm **Khám phá mô hình** → **Đăng ký mô hình**

**Mô hình khả dụng (hơn 100 lựa chọn):**
- OpenAI: `openai/gpt-4o`, `openai/o1`
- Anthropic: `anthropic/claude-sonnet-4.5`, `anthropic/claude-3.5-haiku`
- Google: `google/gemini-3.5-flash`, `google/gemini-2.5-pro`
- Meta: `meta-llama/llama-3.3-70b-instruct`, `meta-llama/llama-3.1-405b-instruct`
- Mistral: `mistralai/mistral-large-2411`
- DeepSeek: `deepseek/deepseek-chat`
- Và nhiều nữa...

**Mô hình giọng nói (Text-to-Speech & Speech-to-Text):**
OpenRouter cũng cung cấp mô hình âm thanh. Bước khám phá sẽ tạo sẵn các mặc định hoạt động; thêm bất kỳ id `vendor/model` nào khác thủ công qua ô nhập mô hình tùy chỉnh.
- Text-to-Speech: `microsoft/mai-voice-2` (dùng tên giọng neural của Microsoft như `en-US-AvaNeural`, không phải bộ `alloy`/`nova` của OpenAI)
- Speech-to-Text: `openai/whisper-1`, `openai/whisper-large-v3`

**Khuyến nghị:**
- Chất lượng: `anthropic/claude-sonnet-4.5` (tổng thể tốt nhất)
- Tốc độ/chi phí: `google/gemini-2.5-flash` (rất nhanh, rẻ)
- Mã nguồn mở: `meta-llama/llama-3.3-70b-instruct`
- Suy luận: `openai/o1`

**Ưu điểm:**
- Một API key cho hơn 100 mô hình
- Thanh toán hợp nhất
- Dễ so sánh mô hình
- Truy cập được các mô hình có thể phải chờ danh sách chờ ở nơi khác

**Ước tính chi phí:**
```
Dùng nhẹ:   1–5 USD/tháng
Dùng vừa:   10–30 USD/tháng
Dùng nhiều: Tùy mô hình chọn
```

**Khắc phục sự cố:**
- "Invalid API key" → Kiểm tra key bắt đầu bằng "sk-or-"
- "Insufficient credits" → Nạp tín dụng tại openrouter.ai
- "Model not available" → Kiểm tra chính tả model ID (dùng đường dẫn đầy đủ)

---

### DashScope (Qwen)

**Chi phí:** ~0,01–0,06 USD / 1K token (tùy mô hình)

**Lấy API Key:**
1. Truy cập https://dashscope.console.aliyun.com/
2. Tạo tài khoản Alibaba Cloud (nếu cần)
3. Vào mục API Keys
4. Tạo API key mới

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **DashScope (Qwen)**
4. Đặt tên, dán API key
5. Bấm **Lưu**, rồi **Kiểm tra kết nối**
6. Bấm **Khám phá mô hình** → **Đăng ký mô hình**

**Mô hình khả dụng:**
- `qwen-max` — Mô hình Qwen mạnh nhất
- `qwen-plus` — Cân bằng chất lượng và tốc độ
- `qwen-turbo` — Nhanh nhất, rẻ nhất

**Khuyến nghị:**
- Chất lượng: `qwen-max` (tổng thể tốt nhất)
- Dùng chung: `qwen-plus` (cân bằng tốt)
- Tốc độ/chi phí: `qwen-turbo` (rẻ nhất)

**Khắc phục sự cố:**
- "Invalid API key" → Kiểm tra key trong console DashScope
- "Model not available" → Khám phá lại mô hình từ credential

---

### MiniMax

**Chi phí:** Tùy mô hình

**Lấy API Key:**
1. Truy cập https://platform.minimaxi.com/
2. Tạo tài khoản (nếu cần)
3. Vào mục API Keys
4. Tạo API key mới

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **MiniMax**
4. Đặt tên, dán API key
5. Bấm **Lưu**, rồi **Kiểm tra kết nối**
6. Bấm **Khám phá mô hình** → **Đăng ký mô hình**

**Mô hình khả dụng:**
- `MiniMax-M2.5` — Mạnh nhất, ngữ cảnh 204K
- `MiniMax-M2.5-highspeed` — Biến thể nhanh hơn, ngữ cảnh 204K

**Khuyến nghị:**
- Chất lượng: `MiniMax-M2.5` (tổng thể tốt nhất)
- Tốc độ: `MiniMax-M2.5-highspeed` (phản hồi nhanh hơn)

**Ưu điểm:**
- Ngữ cảnh rất dài (204K token)
- Giá cạnh tranh

**Khắc phục sự cố:**
- "Invalid API key" → Kiểm tra key trên nền tảng MiniMax
- "Model not available" → Khám phá lại mô hình từ credential

---

### Cohere

**Chi phí:** Theo mức sử dụng

**Lấy API Key:**
1. Truy cập https://dashboard.cohere.com/api-keys
2. Tạo tài khoản (nếu cần)
3. Tạo API key mới

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **Cohere**
4. Đặt tên, dán API key
5. Bấm **Lưu**, rồi **Kiểm tra kết nối**
6. Bấm **Khám phá mô hình** → **Đăng ký mô hình**

**Mô hình khả dụng:**
- `command-a-03-2025` — Mô hình ngôn ngữ Command mới nhất
- `embed-v4.0` — Mô hình embedding mới nhất (chọn loại **Embedding** khi đăng ký)

**Ghi chú:**
- Cohere dùng API v2 gốc của họ (`/v2/chat`, `/v2/embed`), không phải endpoint tương thích OpenAI.
- Chức năng rerank chưa có trong Open Notebook (theo dõi riêng).

**Khắc phục sự cố:**
- "Invalid API key" → Kiểm tra key trong dashboard Cohere
- "Model not available" → Khám phá lại mô hình từ credential

---

### Novita

**Chi phí:** Trả theo mô hình (cạnh tranh)

**Lấy API Key:**
1. Truy cập https://novita.ai/settings/key-management
2. Tạo tài khoản (nếu cần)
3. Tạo API key mới

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **Novita**
4. Đặt tên, dán API key
5. Bấm **Lưu**, rồi **Kiểm tra kết nối**
6. Bấm **Khám phá mô hình** → **Đăng ký mô hình**

**Ghi chú:**
- Novita là cổng tương thích OpenAI (`https://api.novita.ai/openai`) cho các LLM open-weight.

**Khắc phục sự cố:**
- "Invalid API key" → Kiểm tra key trong console Novita
- "Model not available" → Khám phá lại mô hình từ credential

---

### PayPerQ (PPQ)

**Chi phí:** Trả theo mức dùng trên các nhà cung cấp mà nó định tuyến tới

**Lấy API Key:**
1. Truy cập https://ppq.ai
2. Tạo tài khoản (nếu cần)
3. Tạo API key mới

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **PayPerQ**
4. Đặt tên, dán API key
5. Bấm **Lưu**, rồi **Kiểm tra kết nối**
6. Bấm **Khám phá mô hình** → **Đăng ký mô hình**

**Ghi chú:**
- PPQ là cổng đa phương thức tương thích OpenAI (`https://api.ppq.ai/v1`), cung cấp mô hình ngôn ngữ, embedding, speech-to-text và text-to-speech.
- Mô hình khám phá được phân loại theo tên; hãy điều chỉnh loại mô hình khi đăng ký nếu một mô hình bị xếp sai nhóm.

**Khắc phục sự cố:**
- "Invalid API key" → Kiểm tra key trong dashboard PPQ
- "Model not available" → Khám phá lại mô hình từ credential

---

## Tự lưu trữ / Cục bộ (Local)

### Ollama (Khuyến nghị cho Local)

**Chi phí:** Miễn phí (chỉ tốn tiền điện)

**Thiết lập Ollama:**
1. Cài Ollama: https://ollama.ai
2. Chạy Ollama nền: `ollama serve`
3. Tải một mô hình: `ollama pull mistral`

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **Ollama**
4. Đặt tên (ví dụ: "Ollama cục bộ")
5. Nhập base URL:
   - Cùng máy (không Docker): `http://localhost:11434`
   - Docker với Ollama trên host: `http://host.docker.internal:11434`
   - Docker với Ollama trong container: `http://ollama:11434`
6. Bấm **Lưu**, rồi **Kiểm tra kết nối**
7. Bấm **Khám phá mô hình** → **Đăng ký mô hình**

Xem *Hướng dẫn thiết lập Ollama* để biết cấu hình mạng chi tiết.

**Cửa sổ ngữ cảnh (`num_ctx`):**

Mô hình Ollama mặc định dùng cửa sổ ngữ cảnh **8.192 token**. Mặc định này cố tình dè dặt để mô hình chạy ổn định trên GPU phổ thông (≈8GB VRAM) mà không tràn bộ nhớ. Nếu phần cứng của bạn mạnh hơn, hãy đặt giá trị **Context Window (num_ctx)** tùy chọn trên credential Ollama (Quản lý → Mô hình → sửa credential Ollama). Nó áp dụng cho mọi mô hình dùng credential đó. Để trống để giữ mặc định.

- Tăng lên (ví dụ `32768`) khi nạp tài liệu lớn hoặc lịch sử chat dài.
- Nếu gặp lỗi "out of memory", giảm giá trị hoặc để mặc định.

**Mô hình khả dụng:**
- `llama3.3:70b` — Chất lượng tốt nhất (cần 40GB+ RAM)
- `llama3.1:8b` — Khuyến nghị, cân bằng (8GB RAM)
- `qwen2.5:7b` — Rất tốt cho code và suy luận
- `mistral:7b` — Đa dụng tốt
- `phi3:3.8b` — Nhỏ, nhanh (4GB RAM)
- `gemma2:9b` — Mô hình của Google, cân bằng
- Nhiều nữa: dùng `ollama list` để xem

**Khuyến nghị:**
- Chất lượng (có GPU): `llama3.3:70b` (tốt nhất)
- Dùng chung: `llama3.1:8b` (cân bằng tốt nhất)
- Tốc độ/ít bộ nhớ: `phi3:3.8b` (rất nhanh)
- Cho code: `qwen2.5:7b` (xuất sắc về code)

**Yêu cầu phần cứng:**
```
GPU (NVIDIA/AMD):
  8GB VRAM: Chạy hầu hết mô hình tốt
  6GB VRAM: Chạy được, chậm hơn
  4GB VRAM: Chỉ mô hình nhỏ

Chỉ CPU:
  16GB+ RAM: Chậm nhưng chạy được
  8GB RAM: Rất chậm
  4GB RAM: Không khuyến nghị
```

**Ưu điểm:**
- Hoàn toàn riêng tư (chạy cục bộ)
- Miễn phí (chỉ tốn điện)
- Không cần API key
- Chạy offline

**Nhược điểm:**
- Chậm hơn đám mây (trừ khi có GPU)
- Mô hình nhỏ hơn đám mây
- Cần phần cứng cục bộ

**Khắc phục sự cố:**
- "Connection refused" → Ollama chưa chạy hoặc sai URL trong credential
- "Model not found" → Tải về: `ollama pull tên-mô-hình`
- "Out of memory" → Dùng mô hình nhỏ hơn hoặc thêm RAM

---

### oMLX (Apple Silicon)

**Chi phí:** Miễn phí (chỉ tốn điện)

**Yêu cầu:** Mac chip Apple Silicon. oMLX chạy trên host (không chạy trong container Linux).

**Thiết lập oMLX:**
1. Cài từ oMLX (https://omlx.ai/) / jundot/omlx (https://github.com/jundot/omlx)
2. Chạy ở cổng **11435** (mặc định `8000` của oMLX xung đột với SurrealDB):
   ```bash
   OMLX_PORT=11435 omlx serve
   ```
3. Nạp mô hình trong giao diện quản trị oMLX

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **oMLX**
4. Base URL mặc định `http://localhost:11435/v1` (dùng `http://host.docker.internal:11435/v1` nếu Open Notebook chạy trong Docker)
5. API key là tùy chọn (chỉ cần nếu bạn khởi động oMLX với `--api-key`)
6. Bấm **Lưu**, rồi **Kiểm tra kết nối** → **Khám phá mô hình** → **Đăng ký mô hình**

Xem *Hướng dẫn thiết lập oMLX* để biết chi tiết về xung đột cổng và khắc phục sự cố.

---

### LM Studio (Giải pháp local thay thế)

**Chi phí:** Miễn phí

**Thiết lập LM Studio:**
1. Tải LM Studio: https://lmstudio.ai
2. Mở ứng dụng
3. Tải một mô hình từ thư viện
4. Vào tab "Local Server"
5. Khởi động server (cổng mặc định: 1234)

**Cấu hình trong Open Notebook:**
1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **OpenAI-Compatible**
4. Đặt tên (ví dụ: "LM Studio")
5. Nhập base URL: `http://host.docker.internal:1234/v1` (Docker) hoặc `http://localhost:1234/v1` (local)
6. API key: `lm-studio` (giá trị giữ chỗ, LM Studio không yêu cầu)
7. Bấm **Lưu**, rồi **Kiểm tra kết nối**

**Ưu điểm:**
- Giao diện đồ họa (dễ hơn CLI của Ollama)
- Nhiều mô hình
- Chú trọng riêng tư
- Chạy offline

**Nhược điểm:**
- Chỉ desktop (Mac/Windows/Linux)
- Chậm hơn đám mây
- Cần GPU cục bộ

---

### Tùy chỉnh tương thích OpenAI (Custom OpenAI-Compatible)

Cho Text Generation UI, vLLM, hoặc các endpoint tương thích OpenAI khác:

1. Vào **Quản lý** → **Mô hình**
2. Bấm **Thêm Credential**
3. Chọn nhà cung cấp: **OpenAI-Compatible**
4. Nhập base URL của endpoint (ví dụ: `http://localhost:8000/v1`)
5. Nhập API key nếu cần
6. Tùy chọn cấu hình URL riêng cho từng dịch vụ (LLM, Embedding, TTS, STT)
7. Bấm **Lưu**, rồi **Kiểm tra kết nối**

Xem *Thiết lập OpenAI-Compatible* để biết hướng dẫn chi tiết.

---

## Doanh nghiệp (Enterprise)

### Azure OpenAI

**Chi phí:** Như OpenAI (theo mức dùng)

**Cấu hình trong Open Notebook:**
1. Tạo dịch vụ Azure OpenAI trong Azure portal
2. Triển khai mô hình GPT-4/3.5-turbo
3. Lấy endpoint và key
4. Vào **Quản lý** → **Mô hình**
5. Bấm **Thêm Credential**
6. Chọn nhà cung cấp: **Azure OpenAI**
7. Điền: API Key, Endpoint, API Version
8. Tùy chọn cấu hình endpoint riêng theo dịch vụ (LLM, Embedding)
9. Bấm **Lưu**, rồi **Kiểm tra kết nối**

**Ưu điểm:**
- Hỗ trợ cấp doanh nghiệp
- Tích hợp VPC
- Tuân thủ (HIPAA, SOC2, v.v.)

**Nhược điểm:**
- Thiết lập phức tạp hơn
- Chi phí vận hành cao hơn
- Cần tài khoản Azure

---

## Embedding (Cho tính năng Tìm kiếm/Ngữ nghĩa)

Mặc định, Open Notebook dùng embedding của chính nhà cung cấp LLM. Mô hình embedding được khám phá và đăng ký qua cùng hệ thống credential — khi bạn khám phá mô hình từ một credential, các mô hình embedding được liệt kê cùng với mô hình ngôn ngữ.

---

## Chọn nhà cung cấp phù hợp

**1. Không muốn chạy cục bộ và không muốn loay hoay với nhiều nhà cung cấp:**

Dùng OpenAI
- Trên đám mây
- Chất lượng tốt
- Chi phí hợp lý
- Thiết lập đơn giản nhất, hỗ trợ mọi chế độ (text, embedding, tts, stt, v.v.)

**Cho người tiết kiệm:** Groq, OpenRouter hoặc Ollama
- Groq: Đám mây siêu rẻ
- Ollama: Miễn phí, nhưng chạy cục bộ
- OpenRouter: rất nhiều mô hình mã nguồn mở dễ tiếp cận

**Cho ưu tiên riêng tư:** Ollama hoặc LM Studio và Speaches (*TTS cục bộ*, *STT cục bộ*)
- Mọi thứ ở cục bộ
- Chạy offline
- Không gửi API key đi đâu cả

**Cho doanh nghiệp:** Azure OpenAI
- Tuân thủ
- Tích hợp VPC
- Có hỗ trợ

---

## Các bước tiếp theo

1. **Chọn nhà cung cấp** ở trên
2. **Lấy API key** (nếu là đám mây) hoặc cài đặt cục bộ (nếu Ollama)
3. **Đặt `OPEN_NOTEBOOK_ENCRYPTION_KEY`** (bắt buộc để lưu credential)
4. Mở **Quản lý** → **Mô hình** → **Thêm Credential**
5. **Kiểm tra kết nối** để xác minh hoạt động
6. **Khám phá & Đăng ký mô hình** để đưa vào sử dụng
7. **Kiểm tra hoạt động** bằng một cuộc chat thử

> **Nhiều nhà cung cấp**: Bạn có thể thêm credential cho bao nhiêu nhà cung cấp tùy ý. Tạo credential riêng cho từng dự án hoặc thành viên nhóm.

Xong!

---

## Cũ: Biến môi trường (Đã ngưng khuyến nghị)

> **Đã ngưng khuyến nghị**: Cấu hình API key của nhà cung cấp AI bằng biến môi trường đã bị ngưng khuyến nghị. Hãy dùng giao diện Cài đặt. Biến môi trường có thể vẫn hoạt động như phương án dự phòng nhưng không còn là cách khuyến nghị.

Nếu bạn nâng cấp từ phiên bản cũ dùng biến môi trường, hãy vào **Quản lý** → **Mô hình** và bấm nút **Migrate to Database** để nhập các key hiện có vào hệ thống credential.

---

## Liên quan

- **Cấu hình API** — Hướng dẫn quản lý credential chi tiết
- **Tham chiếu biến môi trường** — Danh sách đầy đủ các biến môi trường
- **Cấu hình nâng cao** — Timeout, SSL, tối ưu hiệu năng
- **Thiết lập Ollama** — Hướng dẫn cấu hình Ollama chi tiết
- **OpenAI-Compatible** — LM Studio và các nhà cung cấp tương thích khác
- **Thiết lập TTS cục bộ** — Chuyển văn bản thành giọng nói với Speaches
- **Thiết lập STT cục bộ** — Chuyển giọng nói thành văn bản với Speaches
- **Khắc phục sự cố** — Các vấn đề thường gặp và cách xử lý
