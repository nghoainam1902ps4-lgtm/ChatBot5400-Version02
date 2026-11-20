# Phase 12D5 — Báo cáo an toàn cập nhật offline

**Kết luận:** bộ cập nhật tự động (`scripts/offline/offline_package.py` update / finish / rollback) đã được sửa
theo mọi finding của 12D4 và diễn tập trên Docker thật với image thay thế, nhưng vẫn **EXPERIMENTAL / NOT READY —
không khuyến nghị cho production**: chưa chạy với script vận hành, boot guard, SurrealDB và image ứng dụng thật,
Docker của máy chủ Ubuntu. Đường cập nhật production là **quy trình thủ công**
([OFFLINE_UPDATE_MANUAL_FALLBACK.md](../deployment/OFFLINE_UPDATE_MANUAL_FALLBACK.md)) theo
[hợp đồng tích hợp](../deployment/OFFLINE_UPDATE_INTEGRATION_CONTRACT.md) — IMPLEMENTED, chưa VERIFIED.

## 1. Đánh giá độ phức tạp và đơn giản hóa

12D4 cho thấy state machine của 12D3 có quá nhiều "con trỏ" tới image đã duyệt (override dùng chung,
`compose-command.txt`, file pin, tag rollback) và quá nhiều trạng thái phải giữ đồng bộ — nguồn của R2-12, R2-13,
R2-16, R2-17. 12D5 **bỏ** thay vì vá:

| Bỏ | Thay bằng |
|---|---|
| `image-override.yml` dùng chung + biến môi trường do công cụ tiêm | tag cục bộ của chính file compose triển khai (`DEPLOY_IMAGE_TAG`) là con trỏ duy nhất; biến môi trường và cổng Legal nằm trong cấu hình của đơn vị |
| file pin + sổ sách pin | không cần: mọi đường khởi động đọc cùng file compose; `pin` chỉ còn báo cáo / sửa tag |
| `rollback legal-off/on` ghi override | từ chối; bật / tắt bằng cấu hình cục bộ + script vận hành |
| dùng lại backup theo TTL | mỗi lần chạy một backup, sau khi dừng ghi |
| mốc đối chiếu chụp lại trước mỗi lần tạo lại | baseline **bất biến** của attempt + ảnh chụp dữ liệu (định danh bản ghi) |

Thứ còn lại vẫn phức tạp (công cụ ~5 200 dòng, 22 trường hợp gián đoạn): vì vậy 12D5 thêm một **phương án thủ
công độc lập** (không journal, không lock, chỉ lệnh Docker chuẩn + script vận hành) và giữ bộ tự động ở mức
EXPERIMENTAL cho tới khi nghiệm thu cục bộ (§8 của checklist).

## 2. Theo finding

| Finding | Trạng thái 12D5 | Sửa | Test chính |
|---|---|---|---|
| R2-12 (P1) | FIXED IN CLOUD (cổng cuối: LOCAL) | override riêng của attempt (chỉ image + pull_policy); `approved.json`; chỉ `finish` / `rollback` đã kiểm mới chuyển tag; `compose-command.txt` sinh từ `approved.json`, chỉ file của đơn vị | `test_refused_second_update_leaves_the_recorded_command_starting_the_approved_image`, `test_refused_rollback_changes_nothing`, `test_closing_the_refused_attempt_keeps_the_approved_image`, `test_update_apply_full_flow`, diễn tập Docker thật |
| R2-05 (P1) | FIXED IN CLOUD (LOCAL: SurrealDB thật) | baseline bất biến: container / image / mount / volume (CreatedAt, inode bind mount), schema, ảnh chụp định danh bản ghi 5 bảng; không đọc được = FAIL; cờ `db_changed` / `data_changed` dính, `--acknowledge-data-change` ghi ai / khi nào, không restore | `test_r2_05_*` (bỏ xfail), 6 test evidence_data đảo ngược, `test_data_verdict`, `test_database_restart_*` |
| R2-04 / F-08 | FIXED IN CLOUD (LOCAL: quy trình backup thật) | không TTL; mỗi lần chạy: bảo trì trên image đã duyệt → chờ tác vụ nền → F1 → backup + kiểm restore → F2 == F1 → … → F3 == F1 ngay trước tạo lại; mã backup dùng một lần; **backup của đơn vị theo hai lần chạy** (lead, sau review: lần đầu dừng ghi và yêu cầu backup, lần sau nhận mã mới chỉ khi F1 và container bảo trì không đổi; mã đưa vào lần đầu bị từ chối và đánh dấu đã dùng) | `test_resumed_run_takes_its_own_backup`, `test_jobs_still_running_in_maintenance_stop_the_update_before_the_backup`, `test_a_record_edited_after_the_backup_stops_the_update_before_the_recreate`, `test_an_operator_backup_is_accepted_only_after_the_tool_stopped_the_writes`, `test_an_operator_backup_is_refused_when_the_data_changed_since_it_was_requested`, `test_an_operator_backup_is_refused_when_the_application_was_recreated_since` |
| R2-13 | FIXED IN CLOUD | bản lịch sử ghi trước khi thay `journal.json`; intent trước mỗi chuyển tiếp; `status` / `health` so ở mọi trạng thái; mã 7 lệch, 8 chưa quyết định / gián đoạn | ma trận gián đoạn 22 trường hợp, `test_kill_*`, `test_drift_is_reported_while_a_later_attempt_is_unfinished`, `test_exit_codes_are_documented` |
| R2-15 | FIXED IN CLOUD | `K_intent` (commit để quay về) ghi một lần trước `git fetch`; guard tiếp tục và khôi phục mã nguồn dùng nó | `test_kill_between_source_merge_and_K_step_keeps_the_resume_guard`, các ca git của ma trận |
| R2-16 (F-11) | FIXED IN CLOUD (LOCAL: script vận hành / boot guard) | bỏ pin; `pin` báo cáo, `--apply` sửa tag lũy đẳng, `--undo` từ chối | `test_pin_twice_is_idempotent_and_undo_cannot_strand_the_tag`, `test_kill_during_a_pin_repair_is_reported_and_recoverable`, `test_deploy_tag_follows_every_finished_update` |
| F-11 (P1) | LOCAL VERIFICATION REQUIRED | hợp đồng `DEPLOY_IMAGE_TAG`; `preflight` từ chối mọi vi phạm; trên Docker thật `compose up -d` thường, `docker restart`, lệnh đã ghi đều chạy image đã duyệt | `test_plain_compose_up_keeps_the_approved_image`, `test_preflight_refuses_*`, diễn tập; W-INT-01…10 |
| R2-17 | FIXED IN CLOUD | cổng Legal là cấu hình của đơn vị; lệnh cổng từ chối, không đổi gì | `test_legal_gate_commands_*`, `test_resume_uses_the_legal_gate_of_the_operator_configuration` |
| R2-20 | FIXED IN CLOUD | không publish cổng / `--no-maintenance` ⇒ cần `--writes-stopped-confirmed`, ghi là bằng chứng, không tự nhận "maintenance"; không baseline ⇒ `--to-image` cần `--force-image` | `test_maintenance_is_not_claimed_for_a_service_without_published_ports`, `test_rollback_without_a_journal_needs_force_for_another_image` |
| R2-07 | FIXED IN CLOUD | báo cáo tin cậy ở `STATE_DIR/verified/` (0600); file cạnh gói không được tin; kiểm chủ sở hữu / quyền ghi thư mục gói và cha; `SIGNATURE_POLICY` | `test_r2_07_*` (bỏ xfail), `test_forged_verify_report_does_not_replace_authentication`, `test_signature_policy_required_is_enforced_on_every_use` |
| R2-06 / F-20 | FIXED IN CLOUD (LOCAL: image store cổ điển trên máy thật) | `run_config_sha256`, định dạng 3; cùng layer khác cấu hình ≠ cùng image; bỏ qua manifest attestation của Docker 29; kiểm lại tag ngay trước mỗi `up` | `test_r2_06_*`, `test_image_with_same_layers_but_another_config_is_not_the_packaged_one`, `test_run_config_is_the_same_from_the_archive_and_from_docker_image_inspect`, Docker thật: hash từ archive = hash từ `docker image inspect` |
| R2-08 | FIXED IN CLOUD | `build` đòi nhãn `revision` = commit và `/app/VERSION` khớp; `--allow-unlabelled-image` ⇒ gói `unverified`, máy chủ từ chối | `test_r2_08_*`, `test_build_refuses_an_image_without_provenance` |
| R2-09 | FIXED IN CLOUD | tag phát hành có sẵn trỏ commit khác ⇒ từ chối trước khi đổi gì | `test_r2_09_*`, `test_existing_release_tag_on_another_commit_is_refused` |
| R2-18 | FIXED IN CLOUD | chiếm thư mục dựng nguyên tử dưới khóa theo phiên bản; ghi tên tạm rồi đổi tên; chỉ dọn thứ chính lần chạy tạo ra | `test_failed_rebuild_keeps_the_previous_good_package`, `test_two_builds_racing_are_refused_cleanly` |
| R2-19 | FIXED IN CLOUD | quét trước header tar theo khối 512 byte: GNU long-name / pax > 64 KiB bị từ chối; giới hạn số mục / dung lượng / tỷ lệ trước `tarfile` | `test_pre_authentication_memory_use_is_bounded` (RSS < 50 MB), `test_prescan_accepts_normal_extended_headers_and_refuses_oversized_ones` |
| R2-10 / F-22 (phía công cụ) | LOCAL VERIFICATION REQUIRED | health kiểm file cache tiktoken (SHA-256) rồi nạp bảng mã thật có timeout (không dùng `chunk_text`); file model băm SHA-256 | `test_r2_10_health_probe_asserts_the_encoding_itself` (bỏ xfail), `test_token_probe_asserts_the_cached_encoding_itself[*]`, `test_model_file_with_the_same_size_but_another_content_fails_the_update`; chạy chính script dò với file mã hóa thật đã kiểm SHA-256: `{'ok': True, 'tokens': 522}`, thư mục rỗng: thất bại rõ ràng; `n_vocab` thật = 200 019 (ngưỡng dò ≥ 199 000) |
| R2-22 | LOCAL VERIFICATION REQUIRED | `build-package.ps1` kiểm tag bằng `docker image ls -q` (không chuyển hướng stderr); test tĩnh cấm `2>$null` | `test_build_package_ps1_has_the_same_order_static`; W-PS-01…03 |
| F-26 | FIXED IN CLOUD | (a) qua R2-07. Phần còn lại (lead): mọi thư mục cha của file cấu hình / `allowed_signers` / bản ghi verify phải thuộc root (hoặc người chạy) và không ghi được bởi nhóm / người khác (thư mục sticky được phép); file compose và `MAINTENANCE_OVERRIDE` ghi được bởi bất kỳ ai ⇒ preflight / finish / rollback từ chối trước khi đổi gì, ghi được bởi nhóm / thuộc tài khoản khác ⇒ cảnh báo | `test_config_in_a_folder_writable_by_others_is_refused`, `test_compose_files_writable_by_anybody_are_refused` |
| F-04, F-05, F-09, F-12, F-13, F-14, F-21, F-23, F-24, F-25, F-27, T-02 | xem `PHASE12D5_FINDING_STATUS.json` | | |

## 3. Phát hiện của lead khi rà sau khi gộp (đã sửa trong 12D5)

1. **Backup của đơn vị không gắn được với lúc dừng ghi** (R2-04 còn hở): mã `--backup-reference` đưa vào cùng lần
   chạy vừa dừng ghi chỉ có thể là bản làm TRƯỚC khi dừng ghi. Sửa: giao thức hai lần chạy (§2). Tác nhân offline
   cũng tự ghi nhận rủi ro này trong báo cáo.
2. **Docker giả lập trả `compose ps -q` là khóa cố định** (`c1`), Docker thật trả ID mới sau mỗi lần tạo lại: logic
   "vẫn là container bảo trì của attempt này" chưa từng được kiểm. Sửa bộ giả lập (ID đổi mỗi `up`, `inspect` nhận
   ID); toàn bộ bộ test chạy lại trên bộ giả lập đã sửa.
3. Test tĩnh của `build-package.ps1` chỉ còn khớp nhờ chữ trong comment — siết lại.
4. **F-26** (tác nhân để PARTIAL): thư mục cha của cấu hình, file compose, override bảo trì (§2). Gói giờ luôn
   mang quy trình thủ công (`build` từ chối checkout thiếu nó, trước mọi lệnh Docker).
5. `mypy`: 14 lỗi mới trong công cụ / oracle (công cụ baseline sạch) — sửa, không đổi hành vi.

## 4. Ma trận gián đoạn (Docker giả lập)

`KeyboardInterrupt` tiêm ngay TRƯỚC và ngay SAU lệnh thật: `git fetch`, `git merge/checkout`, `docker load`, `docker
tag` (tag rollback, tag triển khai), mọi `compose up` (dừng ghi, tạo lại của update / finish / rollback), lưu journal
sau finish / rollback — 22 trường hợp. Sau mỗi ca: `status` khác 0 và nêu trạng thái; tag triển khai vẫn ở image đã
duyệt (trừ khi kill sau khi `finish` đã chuyển tag thành công — khi đó `status` báo chuyển tiếp bị gián đoạn);
`rollback` đưa cả image lẫn mã nguồn về đúng chỗ.

## 5. Diễn tập trên Docker thật (Cloud, image thay thế)

Docker 29.10.0, Compose 5.7.1, image store containerd. Hai module, bật bằng `CB5400_REAL_DOCKER=1`:

- `tests/test_offline_real_docker.py` (bộ tự động): build thật (BuildKit, nhãn), `docker save` / `load`; hash cấu
  hình chạy từ archive = từ `docker image inspect`; `compose config / exec / up` với override bảo trì (`!override`
  cổng) và override của attempt; cổng bảo trì thật sự chỉ `127.0.0.1`; `compose up -d` thường trong lúc nghiệm thu
  chạy image đã duyệt; sau `finish`, `compose up -d` thường, `docker restart` và lệnh đã ghi giữ image đã duyệt; ID
  container database không đổi; rollback chuyển tag về; cập nhật bị từ chối không đổi `approved.json` / tag; lần cập
  nhật thứ hai tự backup.
- `tests/test_offline_manual_fallback_real_docker.py` (quy trình thủ công): §2 → §10.1 của tài liệu với đúng dạng
  lệnh; gói bị sửa 1 byte bị `sha256sum -c` chặn; DB container giữ ID / image / mount / dữ liệu suốt quá trình; tag
  phiên bản trong compose (vi phạm C1) không bị chuyển.

Còn LOCAL: Docker của máy chủ Ubuntu và image store cổ điển; image ChatBot5400 thật và các phép dò của nó (ảnh chụp
SurrealDB, cache tiktoken, OCR CLI, thời gian băm model thật); SurrealDB thật; script vận hành, boot guard, override
bảo trì, khởi động lại máy thật; Windows / PowerShell.

## 6. Rủi ro còn lại

- Ảnh chụp dữ liệu chỉ phủ 5 bảng (`source`, `notebook`, `note`, `source_embedding`, `source_insight`); file tải
  lên, cài đặt, credential, lịch sử chat không được chụp. Chi phí đọc nhiều lần mỗi lần chạy chưa đo trên database lớn.
- `FINISH_FAILED`: tag đã về image đã duyệt nhưng container đang chạy image mới ở chế độ thường cho tới khi người vận
  hành `rollback.sh app` (hoặc chạy script vận hành) — log nói rõ; nên rollback ngay.
- Fail-closed có chủ ý: baseline chụp trước khi vào bảo trì (người dùng xóa bản ghi trong khoảng ngắn đó ⇒ attempt
  thất bại); rollback nhiều tuần sau thất bại nếu người dùng đã xóa bản ghi của baseline (cần
  `--acknowledge-data-change`); `compose up -d` thường trong lúc nghiệm thu bị báo lệch (mã 7); journal 12D3 (schema 2)
  chưa quyết định bị từ chối, không chuyển đổi.
- Bằng chứng backup của đơn vị vẫn là lời xác nhận của người vận hành về NỘI DUNG bản backup; công cụ chỉ chứng minh
  được THỜI ĐIỂM (sau khi dừng ghi, dữ liệu không đổi tới lúc tạo lại).

## 7. Kết luận

OFFLINE UPDATE SAFETY: **PARTIAL** — logic giao dịch, tin cậy gói và danh tính image được sửa và kiểm ở Cloud (giả lập
+ Docker thật với image thay thế); an toàn trên môi trường thật (script vận hành, boot guard, SurrealDB, image thật)
chưa được chứng minh. SIMPLIFIED OFFLINE FALLBACK: **IMPLEMENTED** (chưa VERIFIED). AUTOMATIC OFFLINE UPDATER:
**EXPERIMENTAL**.
