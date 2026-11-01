import { useEffect, useRef } from "react";
import { SwitchField } from "@figma/astraui";

type SettingSwitchProps = {
  label: string;
  description: string;
  selected: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  resetKey?: string;
};

/** Keep Astra's switch styling while adding its missing accessible state/label. */
export function SettingSwitch({
  label,
  description,
  selected,
  onChange,
  disabled = false,
  resetKey = "",
}: SettingSwitchProps) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const button = root.current?.querySelector("button");
    button?.setAttribute("role", "switch");
    button?.setAttribute("aria-label", label);
    button?.setAttribute("aria-checked", String(selected));
    button?.setAttribute("type", "button");
  }, [label, selected, resetKey]);
  return (
    <div
      ref={root}
      className="setting-switch-adapter"
      onClick={(event) => {
        if (disabled || (event.target instanceof Element && event.target.closest("button"))) return;
        root.current?.querySelector("button")?.click();
      }}
    >
      <SwitchField
        key={resetKey}
        label={label}
        description={description}
        defaultSelected={selected}
        disabled={disabled}
        onChange={onChange}
      />
    </div>
  );
}
