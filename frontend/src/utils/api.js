const API_BASE = '/api/v1';

class ApiClient {
  constructor() {
    this.base = API_BASE;
    this.token = localStorage.getItem('pharmatrace_token');
  }

  async request(endpoint, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.base}${endpoint}`, {
      ...options,
      headers
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Network error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
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

  async identifyPill(description) {
    return this.request(`/vision/identify?description=${encodeURIComponent(description)}`, { method: 'POST' });
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
}

export const api = new ApiClient();
export default api;
