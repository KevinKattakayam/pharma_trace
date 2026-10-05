import { getToken, setToken as persistToken } from './session';
const configuredBase = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const API_BASE = configuredBase.replace(/\/$/, '');
const DEFAULT_TIMEOUT_MS = 20_000;

class ApiClient {
  constructor() {
    this.base = API_BASE;
  }

  async request(endpoint, options = {}) {
    const token = await getToken();
    const headers = { ...options.headers };
    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs || DEFAULT_TIMEOUT_MS);
    const abortFromCaller = () => controller.abort();
    options.signal?.addEventListener('abort', abortFromCaller, { once: true });

    let response;
    try {
      response = await fetch(`${this.base}${endpoint}`, { ...options, headers, signal: controller.signal });
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The request took too long. Check your connection and try again.');
      throw new Error('Unable to reach PharmaTrace. Check your connection and try again.');
    } finally {
      window.clearTimeout(timeout);
      options.signal?.removeEventListener('abort', abortFromCaller);
    }

    if (!response.ok) {
      const reqId = response.headers.get("X-Request-ID") || "unknown";
      const error = await response.json().catch(() => ({ detail: 'Network error' }));
      console.error(`[API Failure] Endpoint: ${endpoint} | Status: ${response.status} | Request-ID: ${reqId}`, error);
      const errObj = new Error(`${error.detail || `HTTP ${response.status}`} (Req ID: ${reqId})`);
      errObj.requestId = reqId;
      errObj.status = response.status;
      throw errObj;
    }

    return response.json();
  }

  // ═══════════════════════════════════════════════
  // Verification (OpenFDA + WHO GTIN + Cold Chain)
  // ═══════════════════════════════════════════════

  async verifyBarcode(barcode, location = null) {
    return this.request('/verify/barcode', {
      method: 'POST',
      body: JSON.stringify({ barcode, location })
    });
  }

  async verifyImage(imageBase64, location = null) {
    return this.request('/verify/image', {
      method: 'POST',
      body: JSON.stringify({ image: imageBase64, location })
    });
  }

  async getVerification(id) {
    return this.request(`/verify/${id}`);
  }

  async getVerificationHistory() {
    return this.request('/verify/history');
  }

  // ═══════════════════════════════════════════════
  // Drug Interactions (Clinical Database)
  // ═══════════════════════════════════════════════

  async checkInteractions(drugNames) {
    return this.request('/interactions/check', {
      method: 'POST',
      body: JSON.stringify({ drugs: drugNames })
    });
  }

  // ═══════════════════════════════════════════════
  // Drug Details (OpenFDA Labels)
  // ═══════════════════════════════════════════════

  async getDrugDetails(ndc) {
    return this.request(`/drugs/${ndc}`);
  }

  async getSideEffects(ndc, lang = 'en') {
    return this.request(`/drugs/${ndc}/side-effects?lang=${lang}`);
  }

  async getDosageAdvice(ndc, patientData) {
    return this.request(`/drugs/${ndc}/dosage`, {
      method: 'POST',
      body: JSON.stringify(patientData)
    });
  }

  async findGenerics(ndc) {
    return this.request(`/drugs/${ndc}/generics`);
  }

  // ═══════════════════════════════════════════════
  // Translation (LibreTranslate — free, no API key)
  // ═══════════════════════════════════════════════

  async getLanguages() {
    return this.request('/translate/languages');
  }

  async translate(text, target, source = 'en') {
    return this.request(`/translate?text=${encodeURIComponent(text)}&target=${target}&source=${source}`, {
      method: 'POST'
    });
  }

  // ═══════════════════════════════════════════════
  // Barcode Validation (WHO GTIN / GS1)
  // ═══════════════════════════════════════════════

  async validateBarcode(barcode) {
    return this.request(`/barcode/validate?barcode=${encodeURIComponent(barcode)}`, {
      method: 'POST'
    });
  }

  async parseGS1(data) {
    return this.request(`/barcode/parse-gs1?data=${encodeURIComponent(data)}`, {
      method: 'POST'
    });
  }

  // ═══════════════════════════════════════════════
  // Vision AI (GPT-4o Vision)
  // ═══════════════════════════════════════════════

  async analyzeImage(imageBase64) {
    return this.request('/vision/analyze', {
      method: 'POST',
      body: JSON.stringify({ image: imageBase64 })
    });
  }

  async identifyPill(description) {
    return this.request(`/vision/identify?description=${encodeURIComponent(description)}`, {
      method: 'POST'
    });
  }

  // ═══════════════════════════════════════════════
  // Adverse Events (OpenFDA FAERS)
  // ═══════════════════════════════════════════════

  async getAdverseEvents(drugName, limit = 10) {
    return this.request(`/adverse-events/${encodeURIComponent(drugName)}?limit=${limit}`);
  }

  // ═══════════════════════════════════════════════
  // Reports (Community Pharmacovigilance)
  // ═══════════════════════════════════════════════

  async submitReport(reportData) {
    return this.request('/reports', {
      method: 'POST',
      body: JSON.stringify(reportData)
    });
  }

  // Safety-case workflow (quarantine and pharmacist/clinic escalation)
  async createSafetyCase(data) {
    return this.request('/safety-cases', { method: 'POST', body: JSON.stringify(data) });
  }

  async getSafetyCases() {
    return this.request('/safety-cases');
  }

  async updateSafetyCase(id, data) {
    return this.request(`/safety-cases/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(data) });
  }

  async getHeatmapData(bounds = null) {
    const params = bounds ? `?bounds=${JSON.stringify(bounds)}` : '';
    return this.request(`/reports/heatmap${params}`);
  }

  async getOutbreakTimeline(region) {
    return this.request(`/reports/timeline/${region}`);
  }

  // ═══════════════════════════════════════════════
  // Pharmacies (Trust Scoring + PostGIS)
  // ═══════════════════════════════════════════════

  async getNearbyPharmacies(lat, lng, radius = 5000) {
    return this.request(`/pharmacies/nearby?lat=${lat}&lng=${lng}&radius=${radius}`);
  }

  async getPharmacyTrustScore(id) {
    return this.request(`/pharmacies/${id}/trust-score`);
  }

  async submitPharmacyReview(id, review) {
    return this.request(`/pharmacies/${id}/review`, {
      method: 'POST',
      body: JSON.stringify(review)
    });
  }

  // ═══════════════════════════════════════════════
  // Caregiver Dashboard
  // ═══════════════════════════════════════════════

  async generateCaregiverLink() {
    return this.request('/caregiver/link', { method: 'POST' });
  }

  async acceptCaregiverLink(code) {
    return this.request('/caregiver/accept', {
      method: 'POST',
      body: JSON.stringify({ code })
    });
  }

  async getCaregiverDashboard() {
    return this.request('/caregiver/dashboard');
  }

  async getCaregiverAlerts() {
    return this.request('/caregiver/alerts');
  }

  // ═══════════════════════════════════════════════
  // Refill Reminders
  // ═══════════════════════════════════════════════

  async getRefillSchedule() {
    return this.request('/refill/schedule');
  }

  async getPushPublicKey() {
    return this.request('/push/public-key');
  }

  async subscribePush(subscriptionData) {
    return this.request('/push/subscribe', {
      method: 'POST',
      body: JSON.stringify(subscriptionData)
    });
  }

  // ═══════════════════════════════════════════════
  // Batch Verification (Health Workers)
  // ═══════════════════════════════════════════════

  async batchVerify(barcodes) {
    return this.request('/verify/batch', {
      method: 'POST',
      body: JSON.stringify({ barcodes })
    });
  }

  // ═══════════════════════════════════════════════
  // Audit Chain (SHA-256 Immutable Log)
  // ═══════════════════════════════════════════════

  async verifyAuditChain() {
    return this.request('/audit/verify');
  }

  async getAuditLog(limit = 50) {
    return this.request(`/audit/log?limit=${limit}`);
  }

  // ═══════════════════════════════════════════════
  // Cold Chain (Open-Meteo Weather API)
  // ═══════════════════════════════════════════════

  async getColdChainAnalysis(lat, lng) {
    return this.request(`/cold-chain?lat=${lat}&lng=${lng}`);
  }

  // ═══════════════════════════════════════════════
  // System Health
  // ═══════════════════════════════════════════════

  async getHealth() {
    return this.request('/health');
  }

  // ═══════════════════════════════════════════════
  // AI Services (Groq — Llama 3.3 70B)
  // ═══════════════════════════════════════════════

  async analyzeDrug(drugName) {
    return this.request(`/ai/analyze-drug?drug_name=${encodeURIComponent(drugName)}`, { method: 'POST' });
  }

  async explainInteraction(drugA, drugB, knownEffect = '') {
    const params = new URLSearchParams({ drug_a: drugA, drug_b: drugB });
    if (knownEffect) params.append('known_effect', knownEffect);
    return this.request(`/ai/explain-interaction?${params}`, { method: 'POST' });
  }

  // ═══════════════════════════════════════════════
  // LangGraph 6-Agent Pipeline
  // ═══════════════════════════════════════════════

  async agentVerify(barcode, drugNames = [], patientAge = null, patientWeight = null, kidneyFunction = null) {
    const params = new URLSearchParams({ barcode });
    drugNames.forEach(d => params.append('drug_names', d));
    if (patientAge) params.append('patient_age', patientAge);
    if (patientWeight) params.append('patient_weight', patientWeight);
    if (kidneyFunction) params.append('kidney_function', kidneyFunction);
    return this.request(`/agents/verify?${params}`, { method: 'POST' });
  }

  // ═══════════════════════════════════════════════
  // Pharmacy Registration
  // ═══════════════════════════════════════════════

  async registerPharmacy(data) {
    const params = new URLSearchParams(data);
    return this.request(`/pharmacies/register?${params}`, { method: 'POST' });
  }

  // ═══════════════════════════════════════════════
  // Caregiver Medication Management
  // ═══════════════════════════════════════════════

  async addRecipientMedication(code, drugName, ndc = '', confidence = 0) {
    const params = new URLSearchParams({ drug_name: drugName, ndc, confidence: String(confidence) });
    return this.request(`/caregiver/recipient/${code}/medication?${params}`, { method: 'POST' });
  }
  // ═══════════════════════════════════════════════
  // Family Cabinet
  // ═══════════════════════════════════════════════

  async addFamilyMember(data) {
    return this.request('/cabinet/members', { method: 'POST', body: JSON.stringify(data) });
  }

  async getFamilyMembers(userId) {
    return this.request(`/cabinet/members/${userId}`);
  }

  async addCabinetMedicine(data) {
    return this.request('/cabinet/add', { method: 'POST', body: JSON.stringify(data) });
  }

  async getCabinetMedicines(userId) {
    return this.request(`/cabinet/list/${userId}`);
  }

  async checkMedicineSafety(medicineName, memberId) {
    return this.request(`/cabinet/check/${encodeURIComponent(medicineName)}/${memberId}`);
  }

  // ═══════════════════════════════════════════════
  // Doctor Visit Summarizer
  // ═══════════════════════════════════════════════

  async extractPrescriptionImage(imageBase64) {
    return this.request('/prescription/extract-image', {
      method: 'POST',
      body: JSON.stringify({ image: imageBase64 })
    });
  }

  async summarizePrescription(data) {
    return this.request('/prescription/summarize', { method: 'POST', body: JSON.stringify(data) });
  }

  // ═══════════════════════════════════════════════
  // Enterprise: Clinic Admin
  // ═══════════════════════════════════════════════

  async setToken(token) {
    await persistToken(token);
  }

  async loginClinic(email, password) {
    return this.request('/clinic/login', { method: 'POST', body: JSON.stringify({ email, password }) });
  }

  async createClinic(data) {
    return this.request('/clinic/create', { method: 'POST', body: JSON.stringify(data) });
  }

  async getClinicDashboard(clinicId) {
    return this.request(`/clinic/${clinicId}/dashboard`);
  }

  async getClinicWorkers(clinicId) {
    return this.request(`/clinic/${clinicId}/workers`);
  }

  // ═══════════════════════════════════════════════
  // Enterprise: Audit Export
  // ═══════════════════════════════════════════════

  async downloadAuditExport(format = 'csv', startDate = '', endDate = '', clinicId = '') {
    const params = new URLSearchParams({ format });
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (clinicId) params.set('clinic_id', clinicId);

    const headers = {};
    const token = await getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(`${this.base}/audit/export?${params}`, { headers });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Network error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.blob();
  }

  // ═══════════════════════════════════════════════
  // Enterprise: PvPI Adverse Event Reporting
  // ═══════════════════════════════════════════════

  async prefillPvpiReport(data) {
    return this.request('/pvpi/prefill-report', { method: 'POST', body: JSON.stringify(data) });
  }

  async getPvpiReportStatus(verificationId) {
    return this.request(`/pvpi/report-status/${verificationId}`);
  }
}

// ── Safety intelligence (v2) ──
ApiClient.prototype.packCheck = function packCheck(qrPayload, printed) {
  return this.request('/safety/pack-check', { method: 'POST', body: JSON.stringify({ qr_payload: qrPayload || null, printed: printed || null }) });
};
ApiClient.prototype.batchAlerts = function batchAlerts(batch, product) {
  const q = new URLSearchParams({ batch });
  if (product) q.set('product', product);
  return this.request(`/safety/batch-alerts?${q}`);
};
ApiClient.prototype.lasaCheck = function lasaCheck(name, genericName) {
  return this.request('/safety/lasa-check', { method: 'POST', body: JSON.stringify({ name, generic_name: genericName || null }) });
};

ApiClient.prototype.priceCheck = function priceCheck(body) {
  return this.request('/safety/price-check', { method: 'POST', body: JSON.stringify(body) });
};

export const api = new ApiClient();
export default api;
