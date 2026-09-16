import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ALMA Lab — מעבדת עלמה האמפירית",
  description: "מעבדה אינטראקטיבית להשוואת תיאוריות עלמה מול ביקורת ונילה, עם ניסויים ניתנים לשחזור.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="he" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
