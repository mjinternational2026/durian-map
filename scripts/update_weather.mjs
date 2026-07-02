import fs from "node:fs";

const indexPath = "index.html";
const outputPath = "weather-forecast.json";
const dailyLogPath = "weather-daily-log.json";

function extractJsonArray(source, variableName) {
  const marker = `const ${variableName} = `;
  const start = source.indexOf(marker);
  if (start < 0) throw new Error(`Cannot find ${variableName}`);
  const arrayStart = source.indexOf("[", start);
  let depth = 0;
  let inString = false;
  let escape = false;
  for (let i = arrayStart; i < source.length; i++) {
    const ch = source[i];
    if (inString) {
      if (escape) escape = false;
      else if (ch === "\\") escape = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "[") depth++;
    else if (ch === "]") {
      depth--;
      if (depth === 0) return JSON.parse(source.slice(arrayStart, i + 1));
    }
  }
  throw new Error(`Cannot parse ${variableName}`);
}

function areaId(area) {
  return [area.country_en, area.province_en, area.district_en]
    .join("|")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function riskFromForecast(days) {
  const rain3d = days.slice(0, 3).reduce((sum, day) => sum + day.rain_mm, 0);
  const maxTemp = Math.max(...days.slice(0, 3).map((day) => day.tmax_c));
  const wetDays = days.slice(0, 3).filter((day) => day.rain_mm >= 5).length;
  let risk = "低";
  if (rain3d >= 80 || maxTemp >= 38 || wetDays >= 3) risk = "高";
  else if (rain3d >= 40 || maxTemp >= 36 || wetDays >= 2) risk = "中高";
  else if (rain3d >= 15 || maxTemp >= 34 || wetDays >= 1) risk = "中";
  const reasons = [];
  if (rain3d >= 15) reasons.push(`未来3天累计降雨 ${rain3d.toFixed(1)}mm`);
  if (wetDays >= 1) reasons.push(`未来3天有 ${wetDays} 天明显降雨`);
  if (maxTemp >= 34) reasons.push(`最高温 ${maxTemp.toFixed(1)}C`);
  if (!reasons.length) reasons.push("未来3天天气风险低");
  return { risk, rain3d_mm: Number(rain3d.toFixed(1)), max_temp_3d_c: Number(maxTemp.toFixed(1)), wet_days_3d: wetDays, reason: reasons.join("；") };
}

async function fetchForecast(chunk) {
  const params = new URLSearchParams({
    latitude: chunk.map((area) => area.lat).join(","),
    longitude: chunk.map((area) => area.lon).join(","),
    daily: "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
    forecast_days: "14",
    timezone: "auto"
  });
  const response = await fetch(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);
  if (!response.ok) throw new Error(`Open-Meteo ${response.status}`);
  const data = await response.json();
  return Array.isArray(data) ? data : [data];
}

const source = fs.readFileSync(indexPath, "utf8");
const areas = extractJsonArray(source, "areas");
const points = {};
const errors = [];

for (let i = 0; i < areas.length; i += 40) {
  const chunk = areas.slice(i, i + 40);
  try {
    const forecasts = await fetchForecast(chunk);
    forecasts.forEach((forecast, offset) => {
      const area = chunk[offset];
      if (!area || !forecast?.daily) return;
      const days = forecast.daily.time.map((date, idx) => ({
        date,
        rain_mm: Number(forecast.daily.precipitation_sum[idx] ?? 0),
        rain_probability_pct: Number(forecast.daily.precipitation_probability_max[idx] ?? 0),
        tmax_c: Number(forecast.daily.temperature_2m_max[idx] ?? 0),
        tmin_c: Number(forecast.daily.temperature_2m_min[idx] ?? 0)
      }));
      points[areaId(area)] = {
        country_en: area.country_en,
        province_en: area.province_en,
        district_en: area.district_en,
        lat: area.lat,
        lon: area.lon,
        ...riskFromForecast(days),
        days
      };
    });
  } catch (error) {
    errors.push({ chunk_start: i, message: String(error.message || error) });
  }
}

const payload = {
  generated_at: new Date().toISOString(),
  source: "Open-Meteo daily forecast",
  coverage_note: "未来14天天气预报按地图点位坐标自动更新；采收风险为经营提示，不替代当地实测。",
  points,
  errors
};

fs.writeFileSync(outputPath, JSON.stringify(payload, null, 2) + "\n");

function readDailyLog() {
  if (!fs.existsSync(dailyLogPath)) {
    return {
      generated_at: new Date().toISOString(),
      source: "Daily snapshots accumulated from Open-Meteo forecast runs",
      points: {}
    };
  }
  return JSON.parse(fs.readFileSync(dailyLogPath, "utf8"));
}

const dailyLog = readDailyLog();
dailyLog.generated_at = new Date().toISOString();
for (const [id, point] of Object.entries(points)) {
  const today = point.days?.[0];
  if (!today) continue;
  if (!dailyLog.points[id]) {
    dailyLog.points[id] = {
      country_en: point.country_en,
      province_en: point.province_en,
      district_en: point.district_en,
      lat: point.lat,
      lon: point.lon,
      records: []
    };
  }
  const records = dailyLog.points[id].records;
  const snapshot = {
    date: today.date,
    rain_mm: today.rain_mm,
    rain_probability_pct: today.rain_probability_pct,
    tmax_c: today.tmax_c,
    tmin_c: today.tmin_c,
    risk: point.risk,
    rain3d_mm: point.rain3d_mm,
    max_temp_3d_c: point.max_temp_3d_c,
    wet_days_3d: point.wet_days_3d
  };
  const existingIndex = records.findIndex((record) => record.date === snapshot.date);
  if (existingIndex >= 0) records[existingIndex] = snapshot;
  else records.push(snapshot);
  records.sort((a, b) => a.date.localeCompare(b.date));
  if (records.length > 730) records.splice(0, records.length - 730);
}

fs.writeFileSync(dailyLogPath, JSON.stringify(dailyLog, null, 2) + "\n");
