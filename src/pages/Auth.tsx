import { useEffect, useState } from "react"
import { Button, Checkbox, InputField } from "@figma/astraui"
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Clock,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  ShieldCheck,
  User,
} from "lucide-react"
import { ChessBoard, Heading } from "../components"
import { useApp } from "../context"

export default function Auth() {
  const {
    page,
    go,
    authFlow,
    setAuthFlow,
    authEmail,
    setAuthEmail,
    setSignedIn,
    setUsername,
    notify,
  } = useApp()
  const [name, setName] = useState("")
  const [email, setEmail] = useState(authEmail)
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [visible, setVisible] = useState(false)
  const [accepted, setAccepted] = useState(true)
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)
  const [otp, setOtp] = useState(["", "", "", "", "", ""])
  const [countdown, setCountdown] = useState(300)
  const [remember, setRemember] = useState(true)
  useEffect(() => {
    setError("")
    setPassword("")
    setConfirmPassword("")
    setPending(false)
    if (page === "otp") {
      setCountdown(300)
      setOtp(["", "", "", "", "", ""])
    }
  }, [page])
  useEffect(() => {
    if (page !== "otp" || countdown <= 0) return
    const timer = setTimeout(() => setCountdown((n) => n - 1), 1000)
    return () => clearTimeout(timer)
  }, [page, countdown])
  const titles: Record<string, string> = {
    login: "Chào mừng kỳ hữu trở lại",
    register: "Bắt đầu hành trình kỳ thủ",
    forgot: "Quên mật khẩu?",
    otp: "Kiểm tra hộp thư của bạn",
    reset: "Đặt mật khẩu mới",
  }
  const descriptions: Record<string, string> = {
    login: "Đăng nhập để tiếp nối những ván cờ hay.",
    register: "Tham gia cộng đồng. Kết nối đam mê. Hoàn toàn miễn phí.",
    forgot: "Đừng lo, chúng tôi sẽ giúp bạn trở lại bàn cờ.",
    otp: "Nhập mã xác minh gồm 6 chữ số đã được gửi đến",
    reset: "Một mật khẩu mạnh để bảo vệ hành trình của bạn.",
  }
  function delay(action: () => void) {
    setPending(true)
    setError("")
    setTimeout(() => {
      setPending(false)
      action()
    }, 850)
  }
  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (page === "otp") {
      if (countdown <= 0) {
        setError("Mã xác minh đã hết hạn. Vui lòng gửi lại mã mới.")
        return
      }
      if (otp.join("").length !== 6) {
        setError("Vui lòng nhập đủ 6 chữ số của mã xác minh.")
        return
      }
      delay(() => {
        if (authFlow === "reset") go("reset")
        else {
          setSignedIn(true)
          if (name) setUsername(name)
          notify("Xác minh thành công. Chào mừng bạn đến với Kỳ Tiên Hội!")
          go("home")
        }
      })
      return
    }
    if (page === "reset") {
      if (password.length < 8) {
        setError("Mật khẩu cần có ít nhất 8 ký tự.")
        return
      }
      if (password !== confirmPassword) {
        setError("Hai mật khẩu chưa trùng khớp. Vui lòng kiểm tra lại.")
        return
      }
      delay(() => {
        notify("Đã đặt mật khẩu mới. Bạn có thể đăng nhập ngay.")
        go("login")
      })
      return
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError("Vui lòng nhập địa chỉ email hợp lệ.")
      return
    }
    if (page === "forgot") {
      delay(() => {
        setAuthEmail(email)
        setAuthFlow("reset")
        go("otp")
      })
      return
    }
    if (page === "register" && name.trim().length < 3) {
      setError("Tên kỳ thủ cần có ít nhất 3 ký tự.")
      return
    }
    if (password.length < 8) {
      setError("Mật khẩu cần có ít nhất 8 ký tự.")
      return
    }
    if (page === "register" && !accepted) {
      setError("Vui lòng đồng ý với quy tắc cộng đồng để tiếp tục.")
      return
    }
    if (page === "login" && email.startsWith("chuakichhoat")) {
      setError(
        "Tài khoản chưa được kích hoạt. Vui lòng xác minh email để tiếp tục.",
      )
      return
    }
    delay(() => {
      setAuthEmail(email)
      if (page === "register") {
        setAuthFlow("register")
        if (name) setUsername(name.trim())
        go("otp")
      } else {
        setSignedIn(true)
        notify(
          remember
            ? "Đăng nhập thành công. Tùy chọn ghi nhớ đã được chọn trong bản mẫu."
            : "Đăng nhập thành công. Chúc bạn có những ván cờ hay!",
        )
        go("home")
      }
    })
  }
  function updateOtp(index: number, value: string) {
    if (/\D/.test(value)) return
    const next = [...otp]
    next[index] = value.slice(-1)
    setOtp(next)
    if (value && index < 5) document.getElementById(`otp-${index + 1}`)?.focus()
  }
  return (
    <div className="auth-page">
      <div className="auth-visual">
        <div className="eyebrow">KỲ TIÊN HỘI · CỜ TƯỚNG TRỰC TUYẾN</div>
        <Heading level={1}>
          Một bàn cờ.
          <br />
          Vạn điều kết nối.
        </Heading>
        <div className="muted">
          Dù mới bắt đầu hay đã dày dạn kinh nghiệm,
          <br />
          luôn có một kỳ hữu đang chờ bạn.
        </div>
        <div className="auth-board">
          <ChessBoard small />
        </div>
        <div className="auth-quote">
          “Cờ hay không chỉ ở thắng thua,
          <br />
          mà ở người bạn gặp qua từng ván.”
        </div>
      </div>
      <section className="auth-form-panel">
        <Button
          variant="subtle"
          size="small"
          iconStart={<ArrowLeft size={16} />}
          onClick={() =>
            go(page === "login" || page === "register" ? "home" : "login")
          }
          className="back-link"
        >
          {page === "login" || page === "register"
            ? "Về sảnh chính"
            : "Quay lại đăng nhập"}
        </Button>
        <div className="auth-form-icon">
          {page === "otp" ? (
            <Mail size={26} />
          ) : page === "reset" || page === "forgot" ? (
            <ShieldCheck size={26} />
          ) : (
            <span className="brand-symbol">K</span>
          )}
        </div>
        <Heading level={1}>{titles[page]}</Heading>
        <div className="muted auth-description">
          {descriptions[page]}
          {page === "otp" && (
            <div className="auth-email">{authEmail || "kyhuu@example.com"}</div>
          )}
        </div>
        <form className="form-stack auth-form" onSubmit={submit} noValidate>
          {page === "register" && (
            <InputField
              label="Tên kỳ thủ"
              aria-label="Tên kỳ thủ"
              prefix={<User size={16} />}
              value={name}
              onChange={setName}
              placeholder="Bạn muốn được gọi là gì?"
              autoComplete="username"
              maxLength={24}
              required
            />
          )}
          {["login", "register", "forgot"].includes(page) && (
            <InputField
              label="Địa chỉ email"
              aria-label="Địa chỉ email"
              prefix={<Mail size={16} />}
              value={email}
              onChange={setEmail}
              placeholder="ban@example.com"
              type="email"
              autoComplete="email"
              required
            />
          )}
          {["login", "register", "reset"].includes(page) && (
            <InputField
              label={page === "reset" ? "Mật khẩu mới" : "Mật khẩu"}
              aria-label={page === "reset" ? "Mật khẩu mới" : "Mật khẩu"}
              prefix={<Lock size={16} />}
              suffix={
                <Button
                  variant="subtle"
                  size="small"
                  type="button"
                  aria-label={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  className="password-toggle"
                  onClick={() => setVisible((v) => !v)}
                >
                  {visible ? <EyeOff size={16} /> : <Eye size={16} />}
                </Button>
              }
              value={password}
              onChange={setPassword}
              placeholder="Ít nhất 8 ký tự"
              type={visible ? "text" : "password"}
              autoComplete={
                page === "login" ? "current-password" : "new-password"
              }
              required
            />
          )}
          {page === "reset" && (
            <InputField
              label="Nhập lại mật khẩu mới"
              aria-label="Nhập lại mật khẩu mới"
              prefix={<Lock size={16} />}
              value={confirmPassword}
              onChange={setConfirmPassword}
              placeholder="Nhập lại mật khẩu"
              type={visible ? "text" : "password"}
              autoComplete="new-password"
              required
            />
          )}
          {page === "otp" && (
            <>
              <div className="otp-fields">
                {otp.map((digit, i) => (
                  <InputField
                    key={i}
                    id={`otp-${i}`}
                    aria-label={`Chữ số xác minh ${i + 1}`}
                    value={digit}
                    onChange={(v) => updateOtp(i, v)}
                    inputMode="numeric"
                    placeholder="—"
                    maxLength={1}
                    autoComplete={i === 0 ? "one-time-code" : "off"}
                    onKeyDown={(e) => {
                      if (e.key === "Backspace" && !digit && i > 0)
                        document.getElementById(`otp-${i - 1}`)?.focus()
                    }}
                    onPaste={(e) => {
                      const text = e.clipboardData
                        .getData("text")
                        .replace(/\D/g, "")
                        .slice(0, 6)
                      if (text) {
                        e.preventDefault()
                        setOtp(
                          Array.from({ length: 6 }, (_, n) => text[n] || ""),
                        )
                        document
                          .getElementById(`otp-${Math.min(text.length, 5)}`)
                          ?.focus()
                      }
                    }}
                  />
                ))}
              </div>
              <div className={`otp-timer ${countdown === 0 ? "expired" : ""}`}>
                <Clock size={15} />
                {countdown > 0
                  ? `Mã có hiệu lực trong ${Math.floor(countdown / 60)
                      .toString()
                      .padStart(
                        2,
                        "0",
                      )}:${(countdown % 60).toString().padStart(2, "0")}`
                  : "Mã đã hết hạn"}
              </div>
            </>
          )}
          {page === "login" && (
            <div className="between login-options">
              <Checkbox
                label="Ghi nhớ đăng nhập"
                defaultChecked
                onChange={setRemember}
              />
              <Button
                variant="subtle"
                size="small"
                className="text-link"
                onClick={() => go("forgot")}
                type="button"
              >
                Quên mật khẩu?
              </Button>
            </div>
          )}
          {page === "register" && (
            <Checkbox
              label="Tôi đồng ý với quy tắc cộng đồng Kỳ Tiên Hội"
              defaultChecked
              onChange={setAccepted}
            />
          )}
          {error && (
            <div className="error-message" role="alert">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}
          <Button
            type="submit"
            className="button-full auth-submit"
            disabled={pending}
            iconEnd={
              pending ? (
                <Loader2 size={17} className="animate-spin" />
              ) : (
                <ArrowRight size={17} />
              )
            }
          >
            {pending
              ? page === "forgot" || page === "register"
                ? "Đang gửi mã..."
                : "Đang xác nhận..."
              : page === "login"
                ? "Đăng nhập"
                : page === "register"
                  ? "Tạo tài khoản"
                  : page === "forgot"
                    ? "Gửi mã xác minh"
                    : page === "otp"
                      ? "Xác minh email"
                      : "Lưu mật khẩu mới"}
          </Button>
        </form>
        {page === "otp" && (
          <div className="auth-switch">
            Chưa nhận được mã?{" "}
            <Button
              variant="subtle"
              size="small"
              className="text-link"
              disabled={countdown > 270 || pending}
              onClick={() =>
                delay(() => {
                  setCountdown(300)
                  setOtp(["", "", "", "", "", ""])
                  notify("Đã gửi lại mã xác minh mẫu.")
                })
              }
            >
              {pending
                ? "Đang gửi..."
                : countdown > 270
                  ? `Gửi lại sau ${countdown - 270}s`
                  : "Gửi lại mã"}
            </Button>
          </div>
        )}
        {page === "login" && (
          <>
            <div className="auth-switch">
              Chưa có tài khoản?{" "}
              <Button
                variant="subtle"
                size="small"
                className="text-link"
                onClick={() => go("register")}
              >
                Đăng ký ngay
              </Button>
            </div>
            <Button
              variant="subtle"
              size="small"
              className="activation-link"
              onClick={() => {
                setAuthEmail(email || "kyhuu@example.com")
                setAuthFlow("activate")
                go("otp")
              }}
            >
              Tài khoản chưa kích hoạt? Xác minh email
            </Button>
          </>
        )}
        {page === "register" && (
          <div className="auth-switch">
            Đã là kỳ hữu?{" "}
            <Button
              variant="subtle"
              size="small"
              className="text-link"
              onClick={() => go("login")}
            >
              Đăng nhập
            </Button>
          </div>
        )}
        <div className="auth-safety">
          <ShieldCheck size={14} />
          <span>
            {page === "otp"
              ? "Bản mẫu: nhập 6 chữ số bất kỳ để trải nghiệm."
              : "Bản mẫu giao diện. Không lưu hoặc gửi thông tin tài khoản."}
          </span>
        </div>
      </section>
    </div>
  )
}
