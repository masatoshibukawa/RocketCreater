import type {Metadata} from "next";
import type {ReactNode} from "react";
import "./globals.css";
import "./workbench.css";
import "./demo.css";
export const metadata:Metadata={title:"RocketWright | 統合版の機能デモ",description:"既存の統合ワークベンチで、8工程の解析履歴、製作・印刷ファイル、組立PDF、設計説明と打ち上げCGを体験する公開デモ。"};
export default function Layout({children}:{children:ReactNode}){return <html lang="ja"><body>{children}</body></html>;}
