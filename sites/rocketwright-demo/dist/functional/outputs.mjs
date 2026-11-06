export function report(result) {
  const { input: i, metrics: m } = result;
  return `# RocketWright 機能デモ / 解析レポート\n\n計算モデル: ${result.model}\n条件: ${result.conditions}\n\n## 入力\n\n目標高度 ${i.target} m / 材料予算 ${i.budget} 円\n容量 ${i.volume} L / 水の充填率 ${i.fill}% / 初期ゲージ圧 ${i.pressure} kPa\n乾燥質量 ${i.dryMass} g / 搭載質量 ${i.payload} g\nノズル径 ${i.nozzle} mm / パラシュート径 ${i.parachute} m\n\n## 計算結果\n\n最高高度 ${m.apogee_m.toFixed(4)} m\n最高点時刻 ${m.apogee_time_s.toFixed(4)} s\n最大上昇速度 ${m.max_speed_mps.toFixed(4)} m/s\n定常降下速度 ${m.descent_speed_mps.toFixed(4)} m/s\n全飛行時間 ${m.flight_time_s.toFixed(4)} s\n離陸質量 ${m.liftoff_mass_kg.toFixed(4)} kg\n暫定費用 ${m.cost_jpy} 円（基礎1,500円＋パラシュート800円）\n\n## 条件判定\n\n${result.checks.map(c => `- ${c.passed ? '通過' : '未達'}: ${c.label} / ${c.detail}`).join('\n')}\n\n${result.passed ? '設定した計算条件を通過しました。' : '未達の条件があります。'} 実機の適合性や安全性の判定ではありません。\n\n## 仮定と限界\n\n${result.limitations.map(text => '- ' + text).join('\n')}\n\n元の式: rocketwright/physics/water.py, recovery.py, atmosphere.py, cost.py\nブラウザ版: bottle-browser-v1（固定刻みRK4）\n`;
}

export function trajectoryCsv(result) {
  return '\uFEFFt_s,altitude_m,speed_mps,mass_kg\r\n' + result.trace.map(point => [point.t_s, point.altitude_m, point.speed_mps, point.mass_kg].join(',')).join('\r\n') + '\r\n';
}

export function shapeSvg(result) {
  const fillHeight = 220 * result.input.fill / 100;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 390" role="img" aria-label="ペットボトルの表示用概形"><title>容量 ${result.input.volume} L / 充填率 ${result.input.fill}%</title><rect width="260" height="390" fill="#1e1e1e"/><defs><clipPath id="bottle"><path d="M105 65 L155 65 L160 90 Q175 115 175 145 L175 300 Q175 320 158 322 L158 340 L102 340 L102 322 Q85 320 85 300 L85 145 Q85 115 100 90 Z"/></clipPath></defs><path d="M100 70 L130 20 L160 70Z" fill="#67748a" stroke="#a8b8d0"/><path d="M85 270 L55 325 L85 315 M175 270 L205 325 L175 315" fill="#707e98" stroke="#a8b8d0"/><rect x="80" y="${322 - fillHeight}" width="100" height="${fillHeight}" fill="#4b8eb7" clip-path="url(#bottle)"/><path d="M105 65 L155 65 L160 90 Q175 115 175 145 L175 300 Q175 320 158 322 L158 340 L102 340 L102 322 Q85 320 85 300 L85 145 Q85 115 100 90 Z" fill="#bdd4e111" stroke="#a5b7c4" stroke-width="2"/><text x="130" y="367" fill="#c2cbd5" text-anchor="middle" font-size="12" font-family="sans-serif">${result.input.volume} L / 水 ${result.input.fill}%</text><text x="130" y="385" fill="#929292" text-anchor="middle" font-size="9" font-family="sans-serif">表示用の近似 / 製造用ではありません</text></svg>`;
}
