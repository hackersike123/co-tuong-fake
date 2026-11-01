import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useState, type ReactNode } from "react";
import { getInitialLanguage, LANGUAGE_STORAGE_KEY, translateText, type Language } from "./i18n-core";

const LanguageContext = createContext<{
  language: Language;
  toggleLanguage: () => void;
} | null>(null);

const TRANSLATABLE_ATTRIBUTES = ["aria-label", "aria-description", "title", "placeholder", "alt"];
const IGNORE_TEXT_SELECTOR =
  'script,style,code,pre,textarea,[contenteditable="true"],[data-i18n-ignore],.chat-message';
const VI_DESCRIPTION =
  "Kỳ Tiên Hội — Không gian cờ tướng trực tuyến. Luyện tập cùng máy, giao lưu cùng kỳ hữu và tiến bộ qua từng nước cờ.";
const EN_DESCRIPTION =
  "Ky Tien Hoi — an online Xiangqi community. Practice against the computer, play with friends, and improve with every move.";

function storedLanguage(): Language {
  try {
    return getInitialLanguage(localStorage.getItem(LANGUAGE_STORAGE_KEY));
  } catch {
    return "vi";
  }
}

function isIgnoredText(node: Text): boolean {
  return Boolean(node.parentElement?.closest(IGNORE_TEXT_SELECTOR));
}

function translateAttribute(element: Element, name: string, language: Language) {
  const value = element.getAttribute(name);
  if (!value || element.closest("[data-i18n-ignore]")) return;
  const translated = translateText(value, language);
  if (translated !== value) element.setAttribute(name, translated);
}

function translateSubtree(node: Node, language: Language) {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node as Text;
    if (isIgnoredText(text)) return;
    const current = text.data;
    const translated = translateText(current, language);
    if (translated !== current) text.data = translated;
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.DOCUMENT_NODE) return;
  const element = node instanceof Element ? node : null;
  if (element) {
    for (const attribute of TRANSLATABLE_ATTRIBUTES) translateAttribute(element, attribute, language);
  }
  for (const child of Array.from(node.childNodes)) translateSubtree(child, language);
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(storedLanguage);
  const toggleLanguage = useCallback(
    () => setLanguage((current) => (current === "vi" ? "en" : "vi")),
    [],
  );
  useLayoutEffect(() => {
    try {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    } catch {
      // Language switching still works for this session when storage is unavailable.
    }
    document.documentElement.lang = language;
    const description = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (description) description.content = language === "vi" ? VI_DESCRIPTION : EN_DESCRIPTION;

    translateSubtree(document.documentElement, language);
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "characterData" && record.target instanceof Text) {
          translateSubtree(record.target, language);
        } else if (record.type === "childList") {
          for (const node of Array.from(record.addedNodes)) translateSubtree(node, language);
        } else if (record.type === "attributes" && record.target instanceof Element) {
          const attribute = record.attributeName;
          if (attribute && TRANSLATABLE_ATTRIBUTES.includes(attribute))
            translateAttribute(record.target, attribute, language);
        }
      }
    });
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: TRANSLATABLE_ATTRIBUTES,
    });
    return () => observer.disconnect();
  }, [language]);

  const value = useMemo(() => ({ language, toggleLanguage }), [language, toggleLanguage]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const value = useContext(LanguageContext);
  if (!value) throw new Error("LanguageProvider is required");
  return value;
}
