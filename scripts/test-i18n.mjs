import assert from "node:assert/strict";
import { getInitialLanguage, intlLocale, translateText } from "../src/i18n-core.ts";

assert.equal(translateText("Sảnh chính", "en"), "Main Hall");
assert.equal(translateText("Main Hall", "vi"), "Sảnh chính");
assert.equal(translateText("Một câu chưa có trong từ điển", "en"), "Một câu chưa có trong từ điển");
assert.equal(translateText("Đã tạo phòng 42.", "en"), "Room 42 created.");
assert.equal(translateText("Room 42 created.", "vi"), "Đã tạo phòng 42.");
assert.equal(translateText("Xin chào, An", "en"), "Hello, An!");
assert.equal(translateText("2 phòng đang chờ", "en"), "2 rooms waiting");
assert.equal(translateText("2 rooms waiting", "vi"), "2 phòng đang chờ");
assert.equal(translateText("Còn 1.000 Elo để đạt Luyện Khí.", "en"), "Need 1.000 Elo to reach Qi Refining.");
assert.equal(translateText("Ada (quân Đỏ) thắng · 1–0", "en"), "Ada (Red) wins · 1–0");
assert.equal(translateText("Ada (Red) wins · 1–0", "vi"), "Ada (quân Đỏ) thắng · 1–0");
assert.equal(translateText("🐴 Sảnh chính · Kỳ Tiên Hội", "en"), "🐴 Main Hall · Ky Tien Hoi");
assert.equal(translateText("#42 · Phòng riêng tư", "en"), "#42 · Private room");
assert.equal(translateText("13 cảnh giới · 3 tầng mỗi bậc · Ngưỡng riêng của Kỳ Tiên Hội", "en"), "13 realms · 3 levels per rank · Ky Tien Hoi thresholds");
assert.equal(translateText("0 tài khoản có dữ liệu trên máy chủ.", "en"), "0 accounts have server data.");
assert.equal(translateText("  Sảnh chính  ", "en"), "  Main Hall  ");
assert.equal(getInitialLanguage("en"), "en");
assert.equal(getInitialLanguage("vi"), "vi");
assert.equal(getInitialLanguage("fr"), "vi");
assert.equal(getInitialLanguage(null), "vi");
assert.equal(intlLocale("vi"), "vi-VN");
assert.equal(intlLocale("en"), "en-US");

console.log("i18n core tests passed");
