import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {title:'첫사인 · 알바 안심 체크',description:'근로계약서의 빠진 항목과 불리한 조항을 점검 기준서와 비교합니다.',icons:{icon:'/favicon.svg'}};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="ko"><body>{children}</body></html>;}
