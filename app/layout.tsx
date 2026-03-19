import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Tagesschau AI",
  description: "Automatische Zusammenfassungen der 20:00 Uhr Tagesschau, generiert durch Google Gemini.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="de" className="dark">
      <body className={`${inter.className} bg-background text-foreground min-h-screen`}>
        <div className="max-w-4xl mx-auto p-4 md:p-8">
          <header className="mb-12 border-b border-gray-800 pb-6 mt-8">
            <h1 className="text-3xl md:text-5xl font-bold tracking-tight text-white mb-2">Tagesschau<span className="text-blue-500">AI</span></h1>
            <p className="text-gray-400">Automatische Zusammenfassungen der 20 Uhr Ausgabe</p>
          </header>
          <main>
            {children}
          </main>
          <footer className="mt-20 py-6 border-t border-gray-800 text-center text-gray-500 text-sm">
            Generiert mit Google Gemini 2.5 Flash & yt-dlp & Vercel
          </footer>
        </div>
      </body>
    </html>
  );
}
