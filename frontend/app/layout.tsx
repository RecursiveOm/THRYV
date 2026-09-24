import type { Metadata } from "next";
import "./globals.css";
import "./workspace.css";
import { ThemeRoot } from "@/components/appearance";

export const metadata: Metadata = {
  title: "THRYV — Your Personal AI",
  description:
    "A little clarity. A new possibility. Your space to think, create, and move forward with THRYV. Created by Omkar Zunje.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ThemeRoot />
        {children}
      </body>
    </html>
  );
}
