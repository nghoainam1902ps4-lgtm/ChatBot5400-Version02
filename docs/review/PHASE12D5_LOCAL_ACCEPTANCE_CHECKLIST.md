# Phase 12D5 — Checklist nghiệm thu Local (Windows build + máy chủ Ubuntu offline)

Bổ sung cho `PHASE12D4_WINDOWS_ACCEPTANCE_CHECKLIST.md` (thứ tự, quy tắc, hai cổng) và
`PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md` (lệnh chi tiết của các mục mang số cũ). Tài liệu này:
(1) đổi **kỳ vọng** của các mục `[SAU 12D5]` thành kết quả an toàn mà 12D5 đã sửa trong mã;
(2) thêm nhóm mới: tokenizer (W-TOK), PowerShell (W-PS), hợp đồng tích hợp (W-INT), quy trình thủ
công (W-FB). Commit cần nghiệm thu: đầu nhánh `feature/legal-document-normalization` sau 12D5.

## Quy tắc (giữ của 12D4)

- Stack thử: project `chatbot5400-phase12-test`, web `127.0.0.1:8504`, API `127.0.0.1:5057`, chỉ
  loopback, database và thư mục riêng; không dùng database / credential / dữ liệu production.
- PDF nghiệp vụ, model Agri, khóa ký ở lại máy Local; không gửi log / kết quả lên Cloud (chỉ chép
  số liệu, không chép nội dung tài liệu).
- Ghi **Đạt / Không đạt / Không chạy được** cho từng mục, kèm lệnh và đầu ra rút gọn. Kết quả khác
  kỳ vọng: ghi nguyên trạng, không sửa tiêu chí.
- **[RC]** bắt buộc trước RC · **[PROD]** bắt buộc trước production · **[AUTO]** chỉ cần nếu muốn
  đưa bộ cập nhật tự động (hiện EXPERIMENTAL / NOT READY) vào production.

## 1. Tự động trên máy có đủ model [RC]

```powershell
uv run pytest tests/ -q -p no:cacheprovider -rxXs
```

Kỳ vọng: không lỗi mới so với `docs/review/PHASE12D5_REGRESSION_REPORT.md`; 0 xpassed; trên máy có
cache tiktoken thật (`CB5400_TIKTOKEN_CACHE_DIR` hoặc image) các test `needs_real` của
`tests/test_token_utils_offline.py` **chạy** (không skip) và đạt; `tests/test_chunking.py` đạt;
`test_direct_tesseract_layer_is_real` **không** bị skip trong lượt chạy toàn bộ (R2-21).
Với Docker thật: `CB5400_REAL_DOCKER=1 uv run pytest tests/test_offline_real_docker.py -q`.

## 2. Chất lượng Legal trên scan thật [RC]

| Mã | Việc | Kỳ vọng 12D5 |
|---|---|---|
| W-RC-07 (R2-11) | ≥ 10 scan thật có letterhead: item chữ ở lớp furniture xuất hiện MỘT lần (số hiệu, tên đơn vị, footnote) | có trong Markdown **Legal** (cảnh báo `furniture_text_kept`); Standard giữ hành vi v1.2.0 |
| W-RC-08 (R2-01) | item TEXT có ≥ 2 provenance (Docling tự nối) | nối không qua được quy tắc ⇒ tách lại (`upstream_merge_undone`); bỏ gạch nối ⇒ giữ, cảnh báo `upstream_dehyphenation`; đọc từng chỗ: không còn câu ghép sai |
| W-RC-09, W-LEG-03..05, W-LEG-19 (F-02) | số trần ở dải đầu / cuối trang: số khoản thụt đầu dòng, "Số: 0001…", "Kỳ báo cáo: 1/2024…", năm, số có 0 đầu | **không mất số nào**; số trang thật chỉ bị coi là artifact khi đủ điều kiện (docstring `legal_normalizer.py` điểm 1), còn lại `page_number_kept` |
| W-LEG-06, 07, 10, 11, W-LEG-20 (F-03) | footnote `(*)` / `1.` / `¹`, điểm `c )` `a-` `a,`, dòng ngày tháng, đơn vị tính, tiêu đề chạy, dòng ký, phụ lục, bảng | **không có câu ghép sai**; chỗ không nối báo `join_not_made` kèm lý do |
| W-LEG-08, W-LEG-21 (F-06) | ảnh ≥ 30 % trang có caption; ảnh nhỏ (chữ ký, dấu) | placeholder `<!-- image -->` còn với mọi ảnh ≥ 4 % trang; `picture_text_unverified` khi chỉ có caption / vài chữ |
| W-LEG-22 (R2-01) | PDF nhiều văn bản độc lập nối tiếp | dòng cuối văn bản trước và dòng đầu văn bản sau KHÔNG bị nối |
| W-LEG-01, 02, 13 (F-01) | nội dung lặp đầu / cuối trang | giữ, `repeated_line_kept` |
| W-LEG-25 (mới) | in rồi scan 10 fixture `d5_*` (`tests/fixtures/legal`) bằng `phase12-test.ps1 fixtures` | so với `<tên>.gt.txt`: 0 xóa, 0 nối sai, 0 chèn; ghi mọi đảo thứ tự (thứ tự đọc của Docling — không được cảnh báo lúc chạy) |
| W-STD-01..06 | Standard parity với image v1.2.0 | **giống từng byte** (bất kỳ khác biệt = release blocker) |

## 3. Hiển thị, metadata, RAG [RC]

| Mã | Việc | Kỳ vọng 12D5 |
|---|---|---|
| W-LEG-24 (R2-02) | Source Legal có `5*3% (tối đa 15*2)`, `(*) … (*)`, `` `TK01` ``, `$`, `_mã_`, URL có `&`, `<…>`, `~[…]~`, `\` | trang Source hiển thị **đúng chữ in**, không in nghiêng / đậm / code / công thức / danh sách tự sinh; sao chép ra đúng chữ in |
| W-RAG-09 (F-17) | `full_text` Legal có `_`, email, URL có `&` | không có `\_`, `&amp;`; chỉ còn `\#` / `\>` đầu dòng và `&lt;` trước thẻ HTML |
| W-LEG-23 | xử lý lại Source Legal ở Standard; restart; xóa Source | `asset.extraction` biến mất / còn / mất như 12D4 |
| W-LEG-26 (R2-03) | database có `asset.extraction` không phải mapping (sửa tay trên stack thử) | Source vẫn mở được |

## 4. Tokenizer offline [RC] (F-22, R2-10)

| Mã | Việc | Kỳ vọng |
|---|---|---|
| W-TOK-01 | image candidate, `--network none`: `docker run --rm --network none -e OCR_OFFLINE=true --entrypoint /app/.venv/bin/python <img> -c 'from open_notebook.utils.token_utils import main; raise SystemExit(main(["--check"]))'` | `"result": "PASS"`, `cache_problem: null`, < 5 giây |
| W-TOK-02 | như trên với `-e TIKTOKEN_CACHE_DIR=/tmp/empty` | `"result": "FAIL"`, `TokenizerUnavailableError`, không treo (< 5 giây) |
| W-TOK-03 | stack thử, mạng chặn thật, `OCR_OFFLINE=true`, cache hỏng (ghi đè file cache trong container thử) rồi tải PDF | nguồn **thất bại rõ ràng** với thông báo nêu file + SHA-256 mong đợi; không chunk nào được tạo; không treo |
| W-TOK-04 (W-RAG-08) | tỷ lệ token / từ thật trên 5 văn bản tiếng Việt + 2 bảng số | ghi tỷ lệ; so với `docs/review/phase12d5/token_ratio_vietnamese_fixtures.json` |
| W-TOK-05 (W-RAG-10) | mạng chặn thật, chat, tìm kiếm | không treo; log không có `openaipublic.blob.core.windows.net` |
| W-TOK-06 | `healthcheck.sh` / `health` của công cụ trên container thật | bước tokenizer kiểm chính file cache (SHA-256) và nạp bảng mã thật, không dựa vào chunk |

## 5. Build gói [RC]

| Mã | Việc | Kỳ vọng 12D5 |
|---|---|---|
| W-PS-01 (R2-22) | `build-package.ps1 -Version 1.2.0-phase12.5` trên **Windows PowerShell 5.1** khi tag chưa tồn tại | không dừng ở bước kiểm tag (giờ là `docker image ls -q`); build chạy tới cuối |
| W-PS-02 | như trên trên PowerShell 7 | như trên |
| W-PS-03 | chạy lại khi tag đã tồn tại | dừng với "image … already exists" |
| W-OFF-01, 01a, 02, 03 | như 12D4 | như 12D4 |
| W-OFF-38 (R2-18) | build lại cùng phiên bản, ngắt giữa chừng | gói tốt của lần trước và `.sha256` của nó **còn nguyên** |
| W-OFF-39 (R2-08) | `--no-build` với image không có nhãn `revision` / nhãn của commit khác | build **từ chối** (trừ `--allow-unlabelled-image`, khi đó máy chủ từ chối gói) |
| W-OFF-04..07, W-OFF-40 (R2-06) | docker save / load, image store, image cùng layer khác cấu hình | gói định dạng 3 có `run_config_sha256`; image cùng layer khác cấu hình bị **từ chối** |
| W-OFF-09, 10, W-OFF-34 (R2-07) | chữ ký; sửa `manifest.json` + `verify-report.json` cạnh gói | `preflight` / `update` **từ chối** (báo cáo tin cậy ở `STATE_DIR/verified/`); khi khóa đã cài, gói không ký bị từ chối |

## 6. Hợp đồng tích hợp với máy chủ thật [PROD]

Theo `docs/deployment/OFFLINE_UPDATE_INTEGRATION_CONTRACT.md`. Chỉ đọc, trừ W-INT-05.

| Mã | Việc | Kỳ vọng |
|---|---|---|
| W-INT-01 (C1) | `docker compose -p <project> <files> config` | `image` của service ứng dụng là một **tag cục bộ** (không phải số phiên bản / digest / upstream) |
| W-INT-02 (C2) | đọc script vận hành và boot guard | cùng project + cùng danh sách file ở chế độ thường / bảo trì / boot guard |
| W-INT-03 (C3) | lọc `OCR_OFFLINE`, `OCR_RAPIDOCR_PERSISTENT`, `OCR_LEGAL_NORMALIZATION_ENABLED` trong container đang chạy | hai biến đầu `true` (thêm vào cấu hình cục bộ nếu thiếu); Legal vắng / `false` |
| W-INT-04 (C4) | `docker port` ở chế độ bảo trì và thường | bảo trì: chỉ `127.0.0.1`; thường: cổng LAN / Tailscale như cấu hình |
| W-INT-05 (C5) | khởi động lại máy chủ (cửa sổ bảo trì) | ứng dụng lên đúng image mà tag chỉ tới; DB container giữ ID |
| W-INT-06 (C6) | đọc mọi lệnh tạo lại ứng dụng | `--no-deps` hoặc chỉ service ứng dụng; không `down`, `-v`, `pull`, `build` |
| W-INT-07 (C7) | W-TOK-01 trên container production đang chạy (chỉ đọc) | `PASS` |
| W-INT-08 (C8) | tìm `docker-compose.offline-pin.yml`, `image-override.yml` trong script / boot guard | không còn |
| W-INT-09 (C9) | `docker image ls chatbot5400` | image trước cập nhật còn tên rollback |
| W-INT-10 | adapter contract §3 với script vận hành thật | từng điểm 1–5 đạt; sai điểm nào: đơn vị sửa cục bộ trước khi cập nhật |

## 7. Diễn tập quy trình thủ công [PROD] — trên stack cô lập trước, production sau

Theo `docs/deployment/OFFLINE_UPDATE_MANUAL_FALLBACK.md`. Đây là đường cập nhật production.

| Mã | Bước | Kỳ vọng |
|---|---|---|
| W-FB-01 | §3 xác thực: SHA-256 qua kênh riêng, chữ ký, `SHA256SUMS` | `OK` / `Good signature`; thử với gói bị sửa 1 byte ⇒ dừng trước khi giải nén |
| W-FB-02 | §2.3 gói không chứa `.env`, model, DB, khóa | không có dòng nào |
| W-FB-03 | §4 ghi trạng thái; app_image = deploy_tag_image | bằng nhau |
| W-FB-04 | §5 `docker load`, nhãn, tag rollback, tokenizer `--network none` | nhãn = manifest; `PASS` |
| W-FB-05 | §6 bảo trì, tác vụ nền = 0, backup + kiểm restore trên bản sao, F1 == F2 | đạt; thử ghi trong lúc backup ⇒ phát hiện khác nhau |
| W-FB-06 | §7 chuyển tag, tạo lại trong bảo trì; DB container / image / mount không đổi; model không đổi; snapshot không mất gì | đạt |
| W-FB-07 | §8 nghiệm thu chức năng (PDF tổng hợp) | đạt; Legal OFF |
| W-FB-08 | §9 chế độ thường | cùng image; cổng như cấu hình |
| W-FB-09 | khởi động lại máy sau §9 | boot guard lên image mới |
| W-FB-10 | §10 rollback ứng dụng (+ mã nguồn nếu đã đồng bộ) | image cũ, DB không đổi, dữ liệu không mất, khởi động lại máy vẫn image cũ |
| W-FB-11 | cập nhật lại sau rollback, rồi lần cập nhật thứ hai (phiên bản kế) | mỗi lần backup mới; tag đúng; boot guard đúng |
| W-FB-12 | thời gian ngừng dịch vụ đo được ở từng bước | ghi lại |

## 8. Bộ cập nhật tự động [AUTO] — EXPERIMENTAL, chỉ trên stack cô lập

Các mục W-OFF-11…31 của 12D3 / 12D4 với kỳ vọng mới:

| Mã | Kỳ vọng 12D5 (trước khi sửa) |
|---|---|
| W-OFF-33 (R2-05) | xóa nửa số Source / trỏ DB sang volume rỗng sau `update --apply` ⇒ `finish` **từ chối** "DATA CHANGED / DATABASE CHANGED", không restore gì (trước: `completed`) |
| W-OFF-35 (R2-12) | lần hai bị từ chối trước khi tạo lại ⇒ `approved.json`, tag triển khai, `compose-command.txt` **không đổi**; lệnh đã ghi và `compose up -d` thường chạy image đã duyệt; `status` / `health` mã 8 (báo attempt còn mở) (trước: chạy image lần hai, `status` 0) |
| W-OFF-37 (R2-20) | không có `ports:` ⇒ `update --apply` đòi `--writes-stopped-confirmed` và vẫn so F1 == F2 (trước: tự nhận "maintenance") |
| W-OFF-32 (R2-04) | chạy lại sau khi dừng trước tạo lại ⇒ **backup mới** mỗi lần chạy; tham chiếu backup đã dùng bị từ chối |
| W-OFF-36 (R2-16) | không còn file pin; `pin` báo cáo; `pin --apply` sửa tag về image đã duyệt; `pin --undo` bị từ chối |
| W-OFF-41 (R2-13, R2-15) | `kill -9` (a) đầu attempt mới, (b) sau `compose up` của `finish`, (c) trong đồng bộ mã nguồn ⇒ `status` mã 7 / 8 nêu trạng thái; `rollback` đưa cả image lẫn mã nguồn về đúng chỗ |
| W-OFF-14..16 | thay bằng W-INT-05 + `docker restart` / reboot ⇒ image đã duyệt |
| W-OFF-27 | rollback thật về v1.2.0 như 12D4 |

## 9. Cổng

| Cổng | Điều kiện |
|---|---|
| **Trước RC** | §1–§5 đạt; review độc lập của Phase 12D5 không còn P0 / P1 mở; Standard parity byte-identical |
| **Trước production (thủ công)** | RC + §6 và §7 đạt (stack cô lập, rồi production trong cửa sổ bảo trì); khóa ký chính thức; quy trình backup / restore của đơn vị được diễn tập; phê duyệt của chủ dự án |
| **Bộ cập nhật tự động vào production** | thêm §8 đạt toàn bộ trên stack cô lập với script vận hành và boot guard thật; tới lúc đó: **không dùng** cho production |

## Biên bản

Người thực hiện · ngày · commit · máy (Windows / Ubuntu, phiên bản Docker, image store) · kết quả
từng mục · lệch so với kỳ vọng (nguyên văn) · quyết định.
