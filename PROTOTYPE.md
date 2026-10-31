# Kỳ Tiên Hội — Hướng dẫn chạy giao diện

Đây là frontend prototype tiếng Việt, xây dựng với React, TypeScript và Astra
UI. Backend FastAPI nằm riêng trong `app/`, nhưng giao diện hiện vẫn chạy ở chế
độ demo: OTP, phòng, chat, đối thủ và nước đi được mô phỏng, chưa gọi API hoặc
bộ máy luật thật.

## Chạy giao diện

Yêu cầu Node.js 22 và pnpm 10.34.3. Từ thư mục gốc repository:

```powershell
pnpm install --frozen-lockfile
pnpm dev
```

Mở `http://127.0.0.1:8443`. Để tạo và xem trước bản build, dùng `pnpm build`
và sau đó `pnpm preview`. Cách chạy backend và API nằm trong `README.md`.

Các hướng dẫn dưới đây mô tả cách đi qua từng màn hình trong frontend demo.

## Màn hình

| Màn hình                        | Đường dẫn                 |
| ------------------------------- | ------------------------- |
| Sảnh chính                      | `#sanh-chinh`             |
| Thiết lập chơi với máy          | `#choi-voi-may`           |
| Sảnh đấu, tìm kiếm và lọc phòng | `#sanh-dau`               |
| Phòng chờ                       | `#phong-cho`              |
| Ván đấu với máy hoặc kỳ hữu     | `#van-co`                 |
| Lịch sử ván đấu                 | `#lich-su`                |
| Xem lại từng nước cờ            | `#xem-lai`                |
| Bảng Phong Thần                 | `#bang-xep-hang`          |
| Hồ sơ cá nhân                   | `#ho-so`                  |
| Đăng nhập / Đăng ký             | `#dang-nhap` / `#dang-ky` |
| Quên mật khẩu                   | `#quen-mat-khau`          |
| Xác minh OTP                    | `#xac-minh-email`         |
| Đặt mật khẩu mới                | `#mat-khau-moi`           |

Các tác vụ tạo phòng, nhập mật khẩu phòng, chia sẻ, hướng dẫn, cài đặt và chỉnh sửa hồ sơ sử dụng modal thống nhất.

## Các luồng bấm thử

### 1. Đăng ký → OTP → Sảnh

Mở menu hồ sơ ở góc trên phải, chọn **Đăng xuất** để xem giao diện khách, sau đó chọn **Đăng ký**.

- Tên kỳ thủ: ít nhất 3 ký tự.
- Email: đúng định dạng.
- Mật khẩu: ít nhất 8 ký tự; không được lưu hay gửi đến máy chủ.
- OTP: nhập 6 chữ số bất kỳ để minh họa xác minh.
- Mã hết hạn sau 5 phút; nút gửi lại có thời gian chờ 30 giây.
- Có xử lý nhập thiếu, dán mã và di chuyển giữa các ô OTP.
- Ở màn hình đăng nhập, nút **Tài khoản chưa kích hoạt? Xác minh email** minh họa luồng kích hoạt.

Luồng quên mật khẩu đi qua cùng màn OTP, sau đó kiểm tra hai mật khẩu mới trùng khớp và trở về đăng nhập.

### 2. Sảnh → Tạo phòng → Phòng chờ → Ván đấu

- Chọn thời gian 15 / 30 / 60 giây, quyền riêng tư và cho phép khán giả.
- Phòng riêng yêu cầu mật khẩu ít nhất 4 ký tự.
- Phòng chờ hiển thị mã phòng, sao chép mã và liên kết mời.
- Chọn **Mời kỳ thủ mẫu**, sau đó **Đối thủ sẵn sàng (mô phỏng)** để mở nút **Bắt đầu ván cờ**.
- Có thể đổi **Vai trò trải nghiệm** để xem giao diện chủ phòng, người chơi quân Đen hoặc khán giả.
- Thao tác đuổi đối thủ và rời phòng yêu cầu xác nhận.

### 3. Sảnh đấu → Chọn phòng

- Tìm theo tên phòng, tên chủ phòng hoặc mã.
- Lọc theo thời gian và trạng thái.
- Nhập mã có sẵn như `KD2846` để vào nhanh.
- Phòng riêng hiển thị modal mật khẩu; trong bản mẫu chỉ kiểm tra định dạng.
- Phòng đang đấu cho phép vào xem nếu bật khán giả.
- Mục **Xem trạng thái** cuối danh sách cho phép thử đang tải, sảnh trống và lỗi kết nối.

### 4. Chơi với máy → Ván đấu → Kết quả

- Chọn quân Đỏ / Đen và độ khó Dễ / Trung bình / Khó.
- Chọn một quân của bạn, rồi chọn một ô đích.
- Đối thủ phản hồi bằng nước đi mô phỏng, không phải AI chơi cờ thực tế.
- Có gợi ý, đi lại, chơi lại, lật bàn cờ và xác nhận thoát.
- **Thử trạng thái ván cờ** mở các trạng thái chiếu tướng, chiếu bí, hết nước, hết giờ và mất kết nối.
- Mất kết nối tạm dừng đồng hồ lượt đi và chờ tối đa 60 giây.
- Trận trực tuyến có cầu hòa, đầu hàng và chat kèm biểu tượng cảm xúc.
- Kết quả hiển thị lý do, lựa chọn chơi lại / tái đấu và về sảnh. Trận giao lưu cộng/trừ Elo trong phiên demo; ván với máy và khán giả không thay đổi Elo. Không đồng bộ điểm lên máy chủ.

### 5. Hồ sơ → Lịch sử → Xem lại

- Hồ sơ có biểu đồ thành tích, nhịp chơi trong tuần và các dấu ấn.
- Nút **Xem trạng thái kỳ thủ mới** minh họa hồ sơ chưa có ván đấu.
- Lịch sử lọc theo kết quả, thời gian và tên đối thủ.
- **Xem lại** mở biên bản khai cuộc mẫu 12 nước.
- Có bước trước / sau, về khai cuộc, đến nước cuối, phát tự động, lật bàn và chọn trực tiếp ký hiệu nước đi.

## Hệ thống thiết kế

- Component từ `@figma/astraui`: nút, ô nhập, checkbox, switch, select, modal, avatar, badge, tabs và thanh điều hướng.
- Token và kiểu giao diện: `styles/global.css`.
- CSS toàn cục và ánh xạ Tailwind: `src/index.css`.
- Font giao diện: **Instrument Sans** cho chữ tiếng Việt và số. Mặt quân dùng **Noto Serif TC** (bản CJK rút gọn lưu cục bộ), khai báo trong CSS qua `--font-chess`; không thay font giao diện.
- Ánh xạ chữ Hán truyền thống duy nhất nằm trong `src/chess/pieces.ts`. Bàn cờ, quân bị ăn, thiết lập và hướng dẫn dùng chung `PieceGlyph`; xem lại và lịch sử vị trí cũng lấy từ cùng dữ liệu. Tên quân và nhãn hỗ trợ trình đọc màn hình vẫn bằng tiếng Việt.
- Thay các biến `--brand-*`, `--surface-*`, `--text-*`, `--wood-*`, `--space-*`, `--corner-*` và `--type-*` để điều chỉnh toàn bộ giao diện.
- Không chỉnh sửa mã bên trong thư viện Astra.

## Responsive

- Desktop: điều hướng bên trái, nội dung chính và thông tin phụ chia cột.
- Tablet: thu gọn mật độ, điều hướng chuyển sang menu khi cần.
- Mobile: điều hướng dưới màn hình; các trang bàn cờ chuyển sang chế độ tập trung, chat và biên bản đặt dưới bàn.
- Các bảng dữ liệu cuộn ngang trong chính vùng bảng, không làm tràn toàn trang.
- Menu bên cuộn độc lập trên màn hình thấp để Cài đặt và hồ sơ không bị chú thích cuối thanh bên che; thẻ phòng, bục cảnh giới và biểu đồ hồ sơ co giãn tới chiều rộng 320px.
- Tôn trọng tùy chọn giảm chuyển động của hệ điều hành.

## Phạm vi dữ liệu và kỹ thuật

Dữ liệu phòng, ván đấu, điểm Elo và tin nhắn chỉ tồn tại trong phiên hiện tại. Tên/avatar đã xác nhận và tùy chọn hiển thị được lưu riêng trên trình duyệt; không đồng bộ lên máy chủ. Chia sẻ và sao chép sử dụng khả năng của trình duyệt; liên kết mời không đại diện cho phòng trực tuyến thật.

`VITE_SOCKET_IO_URL=""`; chế độ kết nối bị khóa ở demo trong `src/config/connection.ts`. Không tạo Socket.IO client, URL máy chủ hay tên sự kiện. Các tương tác video/micro chỉ đổi trạng thái giao diện, không truy cập thiết bị, thu âm, ghi hình hoặc truyền media.

Thành phần dùng chung nằm trong `src/components.tsx`; dữ liệu mẫu và kiểu miền trong `src/data.ts`; trạng thái liên màn hình trong `src/context.tsx`; màn hình trong `src/pages/`; modal trong `src/dialogs.tsx`.

## Cảnh giới và khung avatar

`src/ranks.ts` là cấu hình duy nhất cho 13 cảnh giới, ngưỡng Elo và số tầng. Đây là quy ước riêng của bản demo, không phải tiêu chuẩn cờ tướng quốc tế. `getCultivationRank` và các thành phần trong `src/rank-ui.tsx` dùng chung trên hồ sơ, Bảng Phong Thần, thẻ người chơi và khung avatar. Các đường dẫn cũ, gồm `#bang-xep-hang`, được giữ nguyên.

`getDemoRankings(elo)` dùng chung thứ tự theo Elo hiện tại cho sảnh, Bảng Phong Thần và thứ hạng hồ sơ. Thẻ phòng hiển thị cả Elo, cảnh giới và tầng từ cùng cấu hình; các số liệu cộng đồng được ghi rõ là demo.

### Khung vinh danh Top 3

Podium sử dụng nguyên bản ba WebP đính kèm trong `public/images/podium/`: Top 1 là `khung-vip-314-v2.webp`, Top 2 là `khung-vip-moc-3.webp`, Top 3 là `khung-vip-moc-4.webp`. Khung dùng `contain`, giữ alpha, nằm trên lớp avatar độc lập; bản PNG lossless của frame đầu tiên trong từng WebP được dùng khi giảm chuyển động hoặc tắt hiệu ứng. Desktop giữ Top 2 – Top 1 – Top 3; mobile xếp Top 1 – Top 2 – Top 3. Màu và kích thước dùng nhóm token `--podium-*` trong CSS.

Dữ liệu kỳ thủ hiện chưa có ảnh chân dung: trường `avatarUrl` là tùy chọn để nhận đúng ảnh thật, không tự gán ảnh người khác. Khi thiếu ảnh, dùng chữ viết tắt hiện có; khi người dùng lọt Top 3, ưu tiên ảnh đại diện đã lưu cục bộ. Không thay đổi Elo, thứ hạng hoặc thống kê.

Podium và ba kỳ thủ dẫn đầu trong bảng dùng chung `PodiumAvatar`; việc chọn khung dựa trên thứ hạng Elo toàn bảng, không dựa vào vị trí hàng sau khi tìm kiếm. Lớp CSS chạy tự động gồm tia sáng quanh viền, hào quang và đốm sáng: Top 1 vàng/trắng nổi bật hơn, Top 2 tím/vàng dịu, Top 3 xanh băng dịu. Avatar không được animate. Các token `--vip-*` điều khiển chu kỳ, ánh sáng, kích thước hàng và khoảng an toàn; chỉ cắt tròn ảnh chân dung, không cắt ảnh khung hay phần đế. Giảm chuyển động hoặc tắt hiệu ứng sẽ dừng cả hoạt cảnh CSS lẫn WebP.

## Ảnh đại diện lưu cục bộ

Hai nút **Chỉnh sửa hồ sơ** và **Tải ảnh đại diện** cùng mở duy nhất **Chỉnh sửa hồ sơ đạo hữu**. Avatar có sẵn, nút chọn ảnh từ thiết bị, xem trước/cắt/xoay và tên kỳ thủ đều nằm trong hộp thoại này, với một bộ **Hủy / Lưu thay đổi**. Chọn hoặc xóa ảnh chỉ sửa bản nháp; Hủy, Escape và đóng hộp thoại bỏ toàn bộ thay đổi chưa lưu.

JPG, PNG, WebP được kiểm tra MIME, chữ ký nội dung và giới hạn 5 MB trước khi giải mã; giữ giới hạn 24 triệu điểm ảnh. `AvatarCropper` tái sử dụng các hàm hình học/canvas trong `avatar.ts`, không mở modal hay tự lưu. Ảnh xuất 256 × 256 thành Blob, loại bỏ metadata và không ghép khung rank vào ảnh. Chỉ bật Lưu khi tên 3–24 ký tự hợp lệ và có thay đổi.

`profile-store.ts` ghi tên, avatar có sẵn và Blob ảnh trong cùng một transaction IndexedDB (`ky-tien-hoi.demo.profile`); `useLocalProfile` chỉ thay trạng thái dùng chung sau khi transaction hoàn tất. Lỗi hết dung lượng/quyền lưu trữ giữ nguyên hồ sơ trước đó và cho phép thử lại. Ảnh localStorage từ phiên bản cũ được chuyển sang IndexedDB trước khi xóa khóa cũ. Object URL được thu hồi khi ảnh bị thay thế hoặc component bị tháo; bitmap và URL giải mã tạm được giải phóng khi bỏ bản nháp.

`UserAvatar`, khung VIP, hồ sơ, menu và danh sách kỳ thủ cùng đọc hồ sơ đã lưu; preset không còn bị ảnh cũ ghi đè. Phòng do người dùng tạo mang cờ sở hữu demo để đổi tên không làm mất nhận diện chủ phòng. Không có HTTP upload hay backend.

## Âm thanh và hiệu ứng

- Âm thanh luôn tắt khi mở ứng dụng; chỉ tạo AudioContext sau thao tác bật của người dùng.
- `src/experience/audio.ts` tự tổng hợp 7 âm quân cờ cùng âm ăn quân, chiếu và chiếu bí bằng Web Audio; không có bản ghi bên ngoài.
- Cài đặt có bật/tắt, âm lượng, nghe thử, âm thanh êm dịu, linh khí, âm dương, giảm chuyển động và đánh dấu nước vừa đi. Các tùy chọn hiển thị/âm lượng được lưu cục bộ; trạng thái bật âm thanh không được tự khôi phục.
- Linh khí nền có mật độ thấp; Thái Cực nằm trong chính board-grid, bên dưới đường kẻ và quân, nên tự theo phối cảnh của bàn nghiêng ở sảnh chính.
- Sảnh chính, sảnh đấu, phòng chờ và ván đấu dùng chung lớp linh khí; bật/tắt trong Cài đặt áp dụng cho tất cả các màn hình này.
- Hiệu ứng kết liễu chỉ chạy khi trạng thái kết thúc có nguyên nhân `checkmate`, không chạy cho ăn quân. Trong prototype, dùng **Thử trạng thái ván cờ → Chiếu bí · Chiến thắng** để minh họa trạng thái đã kết thúc; không bổ sung hay giả vờ có bộ máy luật cờ thật.
- Hiệu ứng kết liễu có thể bỏ qua và tự mở kết quả sau 1,8 giây. Giảm chuyển động hệ thống/tùy chọn sẽ bỏ hoạt cảnh, dừng vòng lặp và mở kết quả ngay. Tắt âm thanh hoặc bỏ qua sẽ ngừng các âm đang được lên lịch.

Lệnh kiểm tra: `pnpm build` và `pnpm exec tsc --noEmit`. Máy chủ preview do môi trường quản lý, không cần khởi động thêm.
