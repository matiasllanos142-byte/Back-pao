import type { Metadata, Viewport } from "next";
import { Open_Sans } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import CartDrawer from "@/components/cart/CartDrawer";
import { CartProvider } from "@/context/CartContext";
import { AuthProvider } from "@/context/AuthContext";
import { OrderProvider } from "@/context/OrderContext";
import { ProductProvider } from "@/context/ProductContext";

const openSans = Open_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-open-sans",
});

export const metadata: Metadata = {
  title: {
    template: "%s | Paola Psicopé",
    default: "Paola Psicopé - Consultorio Psicopedagógico",
  },
  description:
    "Consultorio psicopedagógico y recursos digitales creados por Paola. Materiales diseñados con fundamento para acompañar procesos de aprendizaje.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className={`${openSans.variable} antialiased`}>
      <body className="min-h-screen flex flex-col bg-surface text-text font-sans">
        <AuthProvider>
          <CartProvider>
            <OrderProvider>
              <ProductProvider>
                <Navbar />
                <CartDrawer />
                <main className="flex-1">{children}</main>
                <Footer />
              </ProductProvider>
            </OrderProvider>
          </CartProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
