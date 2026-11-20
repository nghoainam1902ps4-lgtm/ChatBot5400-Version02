# Phase 12D4 — Checklist nghiệm thu Windows Local (sau re-review)

Bổ sung và **sắp lại thứ tự** cho `PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md` (vẫn là nơi có bảng chi tiết và lệnh
của từng mục W-STD / W-RC / W-LEG / W-RAG / W-OFF / W-PIPE mang số cũ). Tài liệu này thêm mục mới từ 12D4, đánh dấu
mục nào chạy được ngay, mục nào phải chờ Phase 12D5, và tách hai cổng: **trước RC** và **trước production**.

## Quy tắc

- Stack thử nghiệm: project `chatbot5400-phase12-test`, web `127.0.0.1:8504`, API `127.0.0.1:5057`, chỉ loopback,
  database và thư mục riêng. **Không** dùng database, credential hay dữ liệu production. Không kết nối production.
- PDF nghiệp vụ và model Agri ở lại máy Local. Công cụ không tự upload, không telemetry. **Không tự động gửi log hay
  kết quả lên Cloud**: khi báo cáo chỉ chép số liệu / dòng log không chứa nội dung tài liệu.
- Mỗi mục ghi **Đạt / Không đạt / Không chạy được**. Kết quả khác kỳ vọng ⇒ ghi lại nguyên trạng, không sửa tiêu chí.
- Ký hiệu: **[RC]** bắt buộc trước RC · **[PROD]** bắt buộc trước production (gồm cả [RC]) · **[NGAY]** chạy được
  trên `8d0c438` · **[SAU 12D5]** kết quả đã biết là không đạt trước khi sửa — chạy bây giờ chỉ để ghi nhận.

## Việc chạy được ngay và có giá trị nhất

Ba nhóm sau **không phụ thuộc** 12D5 và trả lời những câu hỏi mà Cloud không trả lời được; kết quả của chúng quyết
định phạm vi 12D5:

1. **W-RC-01 + W-RC-07** — Layout Heron gắn nhãn gì cho số trang, header, footer, số hiệu văn bản trên scan thật.
2. **W-RC-04 + W-RC-08** — phép nối của Docling có xảy ra trên scan thật không, tần suất.
3. **W-OFF-01, 04, 05, 06** — PowerShell build, bố cục thật của `docker save`, image ID giữa hai image store.

## Thứ tự nghiệm thu

### 1. Kiểm tra môi trường [RC] [NGAY]

```powershell
git fetch origin feature/legal-document-normalization review/phase12d4-fable-reaudit
```

```powershell
git switch feature/legal-document-normalization
```

```powershell
$PSVersionTable.PSVersion; docker version --format '{{.Server.Version}}'; docker info --format '{{.Driver}} {{.DriverStatus}}'
```

```powershell
.\scripts\windows\phase12-test.ps1 check
```

Ghi: commit, phiên bản PowerShell (**cần cả Windows PowerShell 5.1 và PowerShell 7** cho bước 9), phiên bản Docker,
loại image store (W-OFF-04).

### 2. Build hai image: baseline và candidate [RC] [NGAY]

Image v1.2.0 (từ tag `v1.2.0`) và image của nhánh feature (`phase12-test.ps1 build`). Ghi image ID, kích thước.
W-OFF-08: trong image candidate, bảng mã token nạp được với `--network none` trong < 5 giây.

### 3. Standard parity [RC] [NGAY]

W-STD-01..06. `full_text` của cùng một PDF trên hai image, cờ Legal tắt và bật-nhưng-chọn-Tiêu-chuẩn, từng engine:
**giống nhau từng byte**. Bất kỳ khác biệt nào là release blocker.

### 4. Pipeline OCR thật [RC] [NGAY]

W-RC-01..06 (kể cả OCR trực tiếp bằng Agri), cộng:

| Mã | Việc | Ghi lại |
|---|---|---|
| **W-RC-07** | Trên ≥ 10 văn bản scan thật có letterhead: trong `06_items.json`, nhãn và lớp (`content_layer`) của tên đơn vị, **số hiệu văn bản**, quốc hiệu, footnote | Số item có chữ nằm ở lớp furniture mà **chỉ xuất hiện một lần**; chúng có trong `07_markdown_standard.md` không (R2-11) |
| **W-RC-08** | Cùng bộ đó: đếm item TEXT có ≥ 2 provenance (khác trang hoặc khác cột) | Số lượng; đọc từng câu ghép: đúng là một câu hay là hai nội dung khác nhau (R2-01). Tìm chuỗi kiểu "TT- NHNN", từ dính liền ở chỗ ngắt trang |
| **W-RC-09** | Số trần ở dải đầu / cuối trang trên scan thật: số trang, số khoản tách rời, số chứng từ, kỳ báo cáo | Vị trí ngang so với lề đoạn văn; có item nhãn ("Số:", "Kỳ:") cùng dòng không (F-02) |

### 5. Chất lượng Legal

| Mục | Cổng | Khi nào |
|---|---|---|
| W-LEG-01, 02, 13 (F-01) | [RC] | [NGAY] |
| W-LEG-03, 04, 05 (F-02) | [RC] | [SAU 12D5] |
| W-LEG-06, 07, 10, 11 (F-03) | [RC] | [SAU 12D5] |
| W-LEG-08 (F-06) | [RC] | [SAU 12D5] |
| W-LEG-09, 12, 14, 15, 18 | [RC] | [NGAY] |
| **W-LEG-19** — in rồi scan (hoặc dùng `.scan.pdf`) các phản ví dụ của `tests/review_phase12d4/test_normalizer_counterexamples.py`: số khoản thụt đầu dòng, "Số: 0001…", "Kỳ báo cáo: 1/2024…" | [RC] | [SAU 12D5] — trước khi sửa: mất số |
| **W-LEG-20** — footnote nhãn TEXT ký hiệu `(*)` / `1.` / `¹`; điểm `c )`; dòng "ngày … tháng … năm"; tiêu đề chạy viết thường đầu trang | [RC] | [SAU 12D5] — trước khi sửa: câu ghép sai |
| **W-LEG-21** — ảnh ≥ 30% trang (bảng lãi suất được scan thành ảnh) có caption | [RC] | [SAU 12D5] |
| **W-LEG-22** — PDF gồm nhiều văn bản độc lập nối tiếp (quyết định + phụ lục; bộ thông báo): dòng cuối văn bản trước và dòng đầu văn bản sau | [RC] | [NGAY] để ghi nhận R2-01 |

Chuẩn bị ground truth cho tài liệu tổng hợp: `phase12-test.ps1 fixtures` sinh PDF + `<tên>.gt.txt`. Với tài liệu thật,
ground truth do người vận hành tự gõ và đặt cạnh PDF (`<tên>.gt.txt`) — ở lại máy Local.

### 6. Metadata trên SurrealDB thật [RC] [NGAY]

W-LEG-16, W-STD-06, cộng **W-LEG-23**: xử lý lại một Source Legal ở chế độ Tiêu chuẩn ⇒ `asset.extraction` biến mất
(không stale); khởi động lại container ⇒ bản ghi còn; xóa Source ⇒ bản ghi mất.

### 7. Trình duyệt thật [RC] [NGAY]

W-LEG-17, cộng **W-LEG-24** (R2-02): một Source có các dòng `Lãi suất = 5*3% (tối đa 15*2)`, `Mức phí (*) … (*)`,
`` Mã `TK01` ``, `[1]: https://…` — ghi lại chính xác những gì hiển thị ở cả Tiêu chuẩn và Legal, và những gì nhận
được khi sao chép từ trang.

### 8. Chunking và RAG [RC] [NGAY]

W-RAG-01..07, cộng:

| Mã | Việc | Kỳ vọng / ghi lại |
|---|---|---|
| **W-RAG-08** | Trong container (có cache): đo tỷ lệ token / từ thật trên 5 văn bản tiếng Việt và 2 bảng số: `python -c "from open_notebook.utils.token_utils import token_count; t=open('/import/x.txt').read(); print(token_count(t), len(t.split()))"` | Ghi tỷ lệ; so với hệ số 1,3 của ước lượng dự phòng (R2-10) |
| **W-RAG-09** | `full_text` của Source Legal có mã sản phẩm chứa `_`, email, URL có `&` | Ghi lại `\_`, `&amp;`, `&lt;` nếu có (F-17 còn lại); hỏi RAG theo mã / email đó ở cả hai chế độ |
| **W-RAG-10** | Mạng bị chặn thật, chat với một notebook | Không treo; log không có yêu cầu tới `openaipublic.blob.core.windows.net`; ghi mọi tên bảng mã khác `o200k_base` nếu xuất hiện |

### 9. Build gói bằng PowerShell [RC] [NGAY]

W-OFF-01 (gồm 01a: `-Version 1.3.0-rc.1` phải bị từ chối trước khi build), W-OFF-02, 03 — **chạy trên cả Windows
PowerShell 5.1 và PowerShell 7** (R2-22: nếu 5.1 dừng ở `docker image inspect … 2>$null`, ghi nguyên thông báo lỗi).
Thêm **W-OFF-38** (R2-18): build lại cùng phiên bản rồi ngắt giữa chừng ⇒ gói tốt của lần trước **phải còn**
[SAU 12D5: trước khi sửa, nó bị xóa].

### 10. Build gói bằng Bash (WSL2) [RC] [NGAY]

Như bước 9 với `build-package.sh`. Thêm **W-OFF-39** (R2-08): `--no-build` với một image build từ commit khác,
không có nhãn `revision` ⇒ ghi nhận công cụ có từ chối không [SAU 12D5].

### 11. Chữ ký [RC] [NGAY, trừ W-OFF-34]

W-OFF-09, W-OFF-10 (khóa thử, không phải khóa phát hành). Thêm **W-OFF-34** (R2-07) [SAU 12D5]: sau `verify`, bằng
một tài khoản không phải root có quyền ghi thư mục giải nén, sửa `manifest.json` và `verify-report.json` (đặt
`"signed": false`, cập nhật `manifest_sha256`) ⇒ `preflight` **phải từ chối**. Ghi `ls -ld` của thư mục giải nén và
thư mục cha.

**[PROD]**: khóa ký phát hành chính thức được tạo, khóa công khai được chuyển qua kênh tin cậy và cài trên máy chủ.

### 12. Docker save / load [RC] [NGAY]

W-OFF-04, 05, 06, 07. Thêm **W-OFF-40** (R2-06): tạo image cùng layer, khác cấu hình
(`docker commit --change 'ENTRYPOINT ["/bin/sh"]' $(docker create chatbot5400:<ver>) chatbot5400:<ver>` trên máy thử),
rồi `preflight` ⇒ ghi nhận có bị từ chối không [SAU 12D5].

### 13. Cập nhật offline [PROD]

W-OFF-11, 12, 13, 21, 22, 23, 24, 25, 26, 31. [NGAY] cho luồng thành công; các mục sau [SAU 12D5]:

| Mã | Việc | Trước khi sửa |
|---|---|---|
| **W-OFF-33** (R2-05) | Sau `update --apply`, trên stack thử: xóa một nửa số Source (hoặc trỏ container DB sang volume rỗng), rồi `finish --approve` | `finish` báo `completed` |
| **W-OFF-35** (R2-12) | 1 lần cập nhật `completed`; lần hai bị từ chối trước khi tạo lại (`BACKUP_VERIFY_CMD=false`); chạy lệnh trong `compose-command.txt`; `status.sh` | container chạy image lần hai, `status` 0 |
| **W-OFF-37** (R2-20) | Dịch vụ ứng dụng không có `ports:` (sau reverse proxy): `update --apply` | log nói "maintenance" dù không chứng minh được |

### 14. Ghim image [PROD] [SAU 12D5 — cần thiết kế lại]

W-OFF-14, 15, 16, cộng **W-OFF-36** (R2-16): pin sau lần cập nhật thứ hai; pin hai lần rồi undo.

**Trước hết, chủ dự án cung cấp (bằng mô tả, không cần truy cập production):** lệnh / script Compose mà máy chủ thật
dùng cho chạy thường, bảo trì, khởi động lại và sau reboot (boot guard) — có `-f` tường minh không, có `--build`
không, có `COMPOSE_FILE` trong `.env` không. Thiếu thông tin này thì không thiết kế được hợp đồng ghim.

Kiểm trên Docker thật, không phụ thuộc pin: `docker restart <container>` và reboot máy thử **không** qua
`compose up` ⇒ container vẫn ở image mới.

### 15. Backup mới sau rollback [PROD]

W-OFF-17, 18 [NGAY]. Thêm **W-OFF-32** (R2-04) [SAU 12D5]: backup xong, dừng update trước khi tạo lại, thêm một
Source, chạy lại trong 120 phút ⇒ **phải backup lại**; ghi thời điểm vào bảo trì so với thời điểm backup.

### 16. Phục hồi sau gián đoạn [PROD]

W-OFF-19, 20, 29, 30. Thêm **W-OFF-41** (R2-13, R2-15) [SAU 12D5]: `kill -9` (a) ngay sau khi lần cập nhật kế tiếp
bắt đầu, (b) ngay sau `compose up` của `finish`, (c) trong `--sync-source` ngay sau khi checkout đổi — sau mỗi lần:
`status.sh` phải báo trạng thái chưa quyết định và `rollback` phải đưa cả image lẫn mã nguồn về đúng chỗ.

### 17. Rollback thật về v1.2.0 [PROD] [NGAY]

W-OFF-27: database đã có `ocr_text_normalization=legal` và Source Legal có `asset.extraction` ⇒ bản 1.2.0 khởi
động, mở được Source, không OCR lại. Ghi nhận: sửa tiêu đề Source trên 1.2.0 làm mất bản ghi `extraction` (chấp nhận).

### 18. Nâng cấp lại [PROD] [NGAY]

Sau bước 17: cập nhật lại cùng gói ⇒ attempt mới, backup mới, tag rollback mới; cổng Legal đúng như trước rollback.

### 19. Hoạt động khi mạng bị chặn thật [PROD] [NGAY]

W-OFF-12, W-RAG-06, W-RAG-10: `iptables -I DOCKER-USER -j DROP` (gỡ bằng `-D`), `healthcheck.sh --prove-offline`,
OCR với từng engine đã cài (kể cả Agri), tải PDF, chat. Không treo; log không có yêu cầu ra ngoài.

### W-PIPE — bộ test tự động trên máy có đủ model [RC] [NGAY]

W-PIPE-01..05, cộng:

```powershell
uv run pytest tests/review_phase12d4 tests/review_phase12d2 -q -rxX -p no:cacheprovider
```

Kỳ vọng trên `8d0c438`: 129 passed, 42 xfailed, 0 xpassed (xpassed sau 12D5 ⇒ gỡ marker). Trên máy có Internet 3 test
`tests/test_chunking.py` phải PASS. Ghi `test_direct_tesseract_layer_is_real` có bị skip trong lượt chạy toàn bộ
không (R2-21).

## Hai cổng

| Cổng | Điều kiện |
|---|---|
| **Trước RC** | Bước 1–12 và W-PIPE đạt; Phase 12D5 hoàn tất và được rà lại; mọi mục [SAU 12D5] gắn [RC] đạt; không còn finding P0 / P1 mở |
| **Trước production** | Mọi điều kiện RC + bước 13–19 đạt trên stack cô lập với mạng bị chặn thật; hợp đồng ghim image được thống nhất với script vận hành thật; khóa ký chính thức; quy trình backup / restore của máy chủ được diễn tập; phê duyệt của chủ dự án |

## Biên bản

| Bước | Đạt | Không đạt | Không chạy được | Ghi chú |
|---|---|---|---|---|
| 1 Môi trường | | | | |
| 2 Build image | | | | |
| 3 Standard parity | | | | |
| 4 Pipeline thật | | | | |
| 5 Legal | | | | |
| 6 SurrealDB | | | | |
| 7 Trình duyệt | | | | |
| 8 Chunking / RAG | | | | |
| 9 PowerShell | | | | |
| 10 Bash | | | | |
| 11 Chữ ký | | | | |
| 12 save / load | | | | |
| 13 Cập nhật offline | | | | |
| 14 Ghim image | | | | |
| 15 Backup | | | | |
| 16 Gián đoạn | | | | |
| 17 Rollback v1.2.0 | | | | |
| 18 Nâng cấp lại | | | | |
| 19 Mạng bị chặn | | | | |
| W-PIPE | | | | |

Không mục nào ở đây được coi là đạt cho tới khi được chạy trên máy thật. Checklist này không cho phép phát hành RC
hay triển khai production.
