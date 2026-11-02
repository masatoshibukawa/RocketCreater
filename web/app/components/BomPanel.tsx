"use client";

import { apiUrl } from "../lib/api";
import { fmt, fmtJpy } from "../lib/format";
import type { BomItem } from "../lib/types";

interface BomPanelProps {
  bom: BomItem[];
  /** Backend-relative path of the BOM CSV from an export_report tool_result, if any. */
  csvUrl: string | null;
  loading: boolean;
}

function isProvisional(item: BomItem): boolean {
  const s = item.source_or_provisional.trim().toLowerCase();
  return s === "" || s.startsWith("provisional");
}

function fmtMass(kg: number | null): string {
  if (kg === null) return "-";
  if (kg >= 1000) return `${fmt(kg / 1000, 2)} t`;
  if (kg >= 1) return `${fmt(kg, 2)} kg`;
  return `${fmt(kg * 1000, 0)} g`;
}

/** 部品: the BOM table (name, qty, mass, price, provisional tag) and the CSV download when the
 * agent ran export_report. */
export default function BomPanel({ bom, csvUrl, loading }: BomPanelProps) {
  return (
    <div className="panel bom-panel">
      <div className="panel-header">
        <h2 className="panel-title">部品</h2>
        <span className="panel-header-right">
          {bom.length > 0 && <span className="muted">{bom.length} 品目</span>}
          {csvUrl !== null && (
            <a className="link-small" href={apiUrl(csvUrl)} target="_blank" rel="noreferrer" download>
              部品表 CSV
            </a>
          )}
        </span>
      </div>
      {bom.length === 0 ? (
        <div className="empty">{loading ? "部品表を作成中…" : "設計案が届くと部品表を表示します"}</div>
      ) : (
        <div className="table-scroll table-scroll-tall">
          <table className="table">
            <thead>
              <tr>
                <th>品名</th>
                <th className="num">数量</th>
                <th className="num">質量</th>
                <th className="num">価格</th>
              </tr>
            </thead>
            <tbody>
              {bom.map((item, i) => {
                const provisional = isProvisional(item);
                const source = item.source_or_provisional;
                return (
                  <tr key={`${item.item_id}-${i}`} title={source || undefined}>
                    <td>
                      {source.startsWith("http") ? (
                        <a href={source} target="_blank" rel="noreferrer">
                          {item.name}
                        </a>
                      ) : (
                        item.name
                      )}
                      {provisional && <span className="chip chip-provisional">仮置き</span>}
                    </td>
                    <td className="num">{fmt(item.qty, Number.isInteger(item.qty) ? 0 : 2)}</td>
                    <td className="num">{fmtMass(item.mass_kg)}</td>
                    <td className="num">{item.price_jpy === null ? "未定" : fmtJpy(item.price_jpy)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
