/*
 * Rezerv - Frontend Uygulama Mantığı
 *
 * Backend ile aynı origin'den (Flask tarafından servis edilerek) çalışacak
 * şekilde tasarlanmıştır; bu yüzden fetch() session çerezini otomatik
 * gönderir (credentials: "same-origin" varsayılanı yeterlidir).
 *
 * State tamamen bellekte tutulur, sayfa yenilenmeden güncellenir.
 */

const API_BASE = ""; // aynı origin, prefix gerekmiyor

// Not: Ekipman verisi henuz gercek envanterle dogrulanmadi, placeholder listedir.
const EKIPMAN_SECENEKLERI = ["projektor", "tv", "whiteboard", "konferans telefonu", "mikrofon"];

const state = {
  user: null,
  rooms: [],
  reservations: [],
  gecmisim: [],
  favorites: [],
};

// ---------- Yardımcılar ----------

async function api(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    data = null;
  }

  if (!res.ok) {
    const message = (data && data.message) || "Beklenmeyen bir hata oluştu.";
    const error = new Error(message);
    error.status = res.status;
    error.payload = data;
    throw error;
  }

  return data;
}

function el(id) {
  return document.getElementById(id);
}

function showAlert(containerId, message, type = "error") {
  const box = el(containerId);
  if (!box) return;
  box.textContent = message;
  box.className = `alert alert-${type}`;
  box.classList.remove("hidden");
}

function clearAlert(containerId) {
  const box = el(containerId);
  if (!box) return;
  box.classList.add("hidden");
  box.textContent = "";
}

function formatTarih(isoStr) {
  if (!isoStr) return "";
  const d = new Date(isoStr.replace("Z", ""));
  return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "long", year: "numeric" });
}

function formatSaat(isoStr) {
  if (!isoStr) return "";
  const d = new Date(isoStr.replace("Z", ""));
  return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

// ---------- Auth ----------

function initAuthTabs() {
  el("tab-login").addEventListener("click", () => switchAuthTab("login"));
  el("tab-register").addEventListener("click", () => switchAuthTab("register"));
}

function switchAuthTab(which) {
  const isLogin = which === "login";
  el("tab-login").classList.toggle("active", isLogin);
  el("tab-register").classList.toggle("active", !isLogin);
  el("form-login").classList.toggle("hidden", !isLogin);
  el("form-register").classList.toggle("hidden", isLogin);
  clearAlert("auth-alert");
}

async function handleRegister(ev) {
  ev.preventDefault();
  clearAlert("auth-alert");

  const payload = {
    ad_soyad: el("reg-ad-soyad").value.trim(),
    departman: el("reg-departman").value.trim(),
    email: el("reg-email").value.trim(),
    password: el("reg-password").value,
  };

  try {
    await api("/auth/register", { method: "POST", body: payload });
    showAlert("auth-alert", "Kayıt başarılı, şimdi giriş yapabilirsiniz.", "success");
    switchAuthTab("login");
    el("login-email").value = payload.email;
  } catch (err) {
    showAlert("auth-alert", err.message);
  }
}

async function handleLogin(ev) {
  ev.preventDefault();
  clearAlert("auth-alert");

  const payload = {
    email: el("login-email").value.trim(),
    password: el("login-password").value,
  };

  try {
    const data = await api("/auth/login", { method: "POST", body: payload });
    state.user = data.user; // {id, ad_soyad, departman, role}
    await enterApp();
  } catch (err) {
    showAlert("auth-alert", err.message);
  }
}

async function handleLogout() {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch (err) {
    // sessizce gec, zaten cikis yapiliyor
  }
  state.user = null;
  state.rooms = [];
  state.reservations = [];
  state.favorites = [];
  el("tab-admin-btn").classList.add("hidden");
  el("app-view").classList.add("hidden");
  el("auth-view").classList.remove("hidden");
  el("user-box").classList.add("hidden");
  el("login-password").value = "";
}

// ---------- Uygulamaya giriş ----------

async function enterApp() {
  el("auth-view").classList.add("hidden");
  el("app-view").classList.remove("hidden");
  el("user-box").classList.remove("hidden");
  el("user-name").textContent = state.user.ad_soyad;
  el("tab-admin-btn").classList.toggle("hidden", state.user.role !== "admin");

  await Promise.all([loadRooms(), loadReservations(), loadFavorites()]);
  renderRooms();
  renderReservations();
}

// ---------- Odalar ----------

async function loadRooms() {
  try {
    state.rooms = await api("/rooms");
  } catch (err) {
    showAlert("app-alert", "Odalar yüklenemedi: " + err.message);
  }
}

// ---------- Favori odalar ----------

async function loadFavorites() {
  try {
    state.favorites = await api("/rooms/favorites");
  } catch (err) {
    state.favorites = [];
  }
}

function isFavorite(roomId) {
  return state.favorites.some((r) => r.id === roomId);
}

async function toggleFavorite(roomId) {
  try {
    await api(`/rooms/${roomId}/favorite`, { method: "POST" });
    await loadFavorites();
    renderRooms();
    if (!el("panel-favorites").classList.contains("hidden")) {
      renderFavorites();
    }
  } catch (err) {
    showAlert("app-alert", "Favori güncellenemedi: " + err.message);
  }
}

function renderFavorites() {
  const grid = el("favorites-grid");
  grid.innerHTML = "";
  if (state.favorites.length === 0) {
    grid.innerHTML = '<div class="empty-state">Henüz favori odanız yok. Oda kartlarındaki ☆ ikonuna tıklayarak ekleyebilirsiniz.</div>';
    return;
  }
  state.favorites.forEach((room) => grid.appendChild(createRoomCard(room, { showLocation: true })));
}

// ---------- Ortak oda kartı üretimi ----------

/** Odalar sekmesi, Boş Oda Bul sonuçları ve Favoriler panelinin ortak
 * kullandığı oda kartı. Pasif odalarda buton disabled ve rozet gösterilir. */
function createRoomCard(room, opts = {}) {
  const { showLocation = false, onReserve = null } = opts;

  const card = document.createElement("div");
  card.className = "room-card" + (room.is_active ? "" : " room-card-inactive");

  const ekipman = (room.ekipman || []).map((e) => `<span class="tag">${e}</span>`).join("");
  const favorited = isFavorite(room.id);

  card.innerHTML = `
    ${!room.is_active ? '<span class="badge-inactive">Kullanım Dışı</span>' : ""}
    <div class="room-card-top">
      <h3>${room.ad}</h3>
      <button type="button" class="favorite-btn ${favorited ? "favorited" : ""}" title="Favorilere ekle/çıkar">${favorited ? "★" : "☆"}</button>
    </div>
    <div class="meta">
      ${showLocation ? `<div>📍 ${floorLabel(room.konum)}</div>` : ""}
      <div>👥 ${room.kapasite} kişi kapasiteli</div>
    </div>
    <div>${ekipman}</div>
    <button type="button" class="btn btn-sm reserve-btn" style="margin-top:10px" ${room.is_active ? "" : "disabled"}>
      ${room.is_active ? "Rezervasyon Yap" : "Kullanım Dışı"}
    </button>
  `;

  card.querySelector(".favorite-btn").addEventListener("click", () => toggleFavorite(room.id));

  if (room.is_active) {
    card.querySelector(".reserve-btn").addEventListener("click", () => {
      if (onReserve) onReserve(room);
      else openReservationModal(room.id);
    });
  }

  return card;
}

// ---------- Kat sirasi ve isimlendirme ----------

const WORK_START = 8 * 60;  // 08:00 (dakika)
const WORK_END = 18 * 60;   // 18:00 (dakika)

function floorLabel(konum) {
  if (konum === "Kat Zemin") return "Zemin Kat";
  return konum;
}

function floorSortIndex(konum) {
  if (konum === "Kat B3") return 0;
  if (konum === "Kat Zemin") return 1;
  const m = konum.match(/^Kat (\d+)$/);
  if (m) return 1 + parseInt(m[1], 10);
  if (konum === "Diğer Lokasyon") return 999;
  return 500;
}

function roomMatchesSearch(room, term) {
  if (!term) return true;
  const t = term.toLocaleLowerCase("tr-TR");
  return (
    room.ad.toLocaleLowerCase("tr-TR").includes(t) ||
    room.konum.toLocaleLowerCase("tr-TR").includes(t) ||
    String(room.kapasite).includes(t)
  );
}

function renderRooms() {
  const container = el("room-groups");
  const term = el("room-search") ? el("room-search").value.trim() : "";
  container.innerHTML = "";

  const select = el("res-room");
  select.innerHTML = '<option value="">Oda seçiniz</option>';
  state.rooms
    .filter((r) => r.is_active) // pasif odalar rezervasyon icin secilemez
    .forEach((room) => {
      const opt = document.createElement("option");
      opt.value = room.id;
      opt.textContent = `${room.ad} (${floorLabel(room.konum)}, ${room.kapasite} kişi)`;
      select.appendChild(opt);
    });

  const filtered = state.rooms.filter((r) => roomMatchesSearch(r, term));

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-state">Aramanızla eşleşen oda bulunamadı.</div>';
    return;
  }

  const gruplar = {};
  filtered.forEach((room) => {
    if (!gruplar[room.konum]) gruplar[room.konum] = [];
    gruplar[room.konum].push(room);
  });

  const katAdlari = Object.keys(gruplar).sort((a, b) => floorSortIndex(a) - floorSortIndex(b));
  const aramaAktif = term.length > 0;

  katAdlari.forEach((kat) => {
    const odalar = gruplar[kat];

    const details = document.createElement("details");
    details.className = "room-group";
    if (aramaAktif) details.open = true;

    const summary = document.createElement("summary");
    summary.innerHTML = `<span>${floorLabel(kat)}</span><span class="room-group-count">${odalar.length} oda</span>`;
    details.appendChild(summary);

    const grid = document.createElement("div");
    grid.className = "room-grid";

    odalar.forEach((room) => {
      grid.appendChild(createRoomCard(room, { showLocation: false }));
    });

    details.appendChild(grid);
    container.appendChild(details);
  });
}

// ---------- Rezervasyonlar ----------

async function loadReservations() {
  try {
    state.reservations = await api("/reservations");
  } catch (err) {
    showAlert("app-alert", "Rezervasyonlar yüklenemedi: " + err.message);
  }
}

function roomAdi(roomId) {
  const room = state.rooms.find((r) => r.id === roomId);
  return room ? room.ad : `Oda #${roomId}`;
}

function renderReservations() {
  const list = el("reservation-list");
  list.innerHTML = "";

  const simdi = new Date();
  const gelecekRezervasyonlar = state.reservations
    .filter((r) => new Date(r.end_time.replace("Z", "")) >= simdi)
    .sort((a, b) => new Date(a.start_time) - new Date(b.start_time));

  if (gelecekRezervasyonlar.length === 0) {
    list.innerHTML = '<div class="empty-state">Yaklaşan rezervasyon bulunmuyor.</div>';
    return;
  }

  gelecekRezervasyonlar.forEach((r) => {
    const item = document.createElement("div");
    item.className = "reservation-item";
    item.innerHTML = `
      <div class="info">
        <strong>${r.baslik}</strong>
        <span>${roomAdi(r.room_id)} · ${formatTarih(r.start_time)} · ${formatSaat(r.start_time)}-${formatSaat(r.end_time)} · ${r.katilimci_sayisi} kişi</span>
      </div>
      <button class="btn btn-sm btn-danger" data-res-id="${r.id}">İptal Et</button>
    `;
    item.querySelector("button").addEventListener("click", () => cancelReservation(r.id));
    list.appendChild(item);
  });
}

async function cancelReservation(id) {
  if (!confirm("Bu rezervasyonu iptal etmek istediğinize emin misiniz?")) return;
  try {
    await api(`/reservations/${id}`, { method: "DELETE" });
    await loadReservations();
    renderReservations();
    // Gecmisim sekmesi de acikta olabilecegi icin, orayi da guncel tut
    if (!el("panel-history").classList.contains("hidden")) {
      await loadGecmisim();
    }
  } catch (err) {
    showAlert("app-alert", "İptal edilemedi: " + err.message);
  }
}

// ---------- Boş Oda Bul ----------

function renderEkipmanCheckboxes() {
  const group = el("find-ekipman-group");
  group.innerHTML = "";
  EKIPMAN_SECENEKLERI.forEach((ekipman, i) => {
    const id = `find-ekip-${i}`;
    const label = document.createElement("label");
    label.className = "checkbox-item";
    label.setAttribute("for", id);
    label.innerHTML = `<input type="checkbox" id="${id}" value="${ekipman}" /> ${ekipman}`;
    const input = label.querySelector("input");
    input.addEventListener("change", () => label.classList.toggle("checked", input.checked));
    group.appendChild(label);
  });
}

function seciliEkipmanlar() {
  return Array.from(el("find-ekipman-group").querySelectorAll("input:checked")).map((i) => i.value);
}

async function handleFindSubmit(ev) {
  ev.preventDefault();
  clearAlert("find-alert");
  el("find-results").innerHTML = "";

  const date = el("find-date").value;
  const startStr = el("find-start").value;
  const endStr = el("find-end").value;
  const katilimci = parseInt(el("find-katilimci").value, 10);
  const istenenEkipman = seciliEkipmanlar();

  if (!date || !startStr || !endStr || !katilimci) {
    showAlert("find-alert", "Lütfen tarih, saat aralığı ve katılımcı sayısını girin.");
    return;
  }

  const istenenBaslangic = saatToDk(startStr);
  const istenenBitis = saatToDk(endStr);
  if (istenenBitis <= istenenBaslangic) {
    showAlert("find-alert", "Bitiş saati başlangıçtan sonra olmalı.");
    return;
  }

  let gununRezervasyonlari;
  try {
    gununRezervasyonlari = await api(`/reservations?date=${date}`);
  } catch (err) {
    showAlert("find-alert", "Rezervasyonlar sorgulanamadı: " + err.message);
    return;
  }

  const uygunOdalar = state.rooms.filter((room) => {
    if (!room.is_active) return false; // pasif odalar rezervasyon icin onerilmez
    if (room.kapasite < katilimci) return false;
    const roomEkipman = room.ekipman || [];
    const ekipmanUyuyor = istenenEkipman.every((e) => roomEkipman.includes(e));
    if (!ekipmanUyuyor) return false;

    const bosluklar = odaBosAraliklari(room.id, gununRezervasyonlari);
    return bosluklar.some((b) => istenenBaslangic >= b[0] && istenenBitis <= b[1]);
  });

  uygunOdalar.sort((a, b) => a.kapasite - b.kapasite);
  renderFindResults(uygunOdalar, date, startStr, endStr);
}

function renderFindResults(odalar, date, startStr, endStr) {
  const box = el("find-results");
  if (odalar.length === 0) {
    box.innerHTML = '<div class="empty-state">Bu kriterlere uygun müsait oda bulunamadı.</div>';
    return;
  }

  box.innerHTML = "";
  odalar.forEach((room) => {
    const card = createRoomCard(room, {
      showLocation: true,
      onReserve: (r) => {
        openReservationModal(r.id);
        el("res-date").value = date;
        el("res-start").value = startStr;
        el("res-end").value = endStr;
      },
    });
    box.appendChild(card);
  });
}

// ---------- Geçmişim ----------

function formatOlusturmaZamani(sqliteStr) {
  // sqlite datetime('now') -> "YYYY-MM-DD HH:MM:SS", UTC varsayilir
  if (!sqliteStr) return "";
  const d = new Date(sqliteStr.replace(" ", "T") + "Z");
  return d.toLocaleString("tr-TR", { day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

async function loadGecmisim() {
  try {
    state.gecmisim = await api("/reservations?mine=true");
  } catch (err) {
    showAlert("app-alert", "Geçmiş yüklenemedi: " + err.message);
    state.gecmisim = [];
  }
}

function renderGecmisim() {
  const list = el("history-list");
  list.innerHTML = "";

  const gecmisim = (state.gecmisim || []).slice().sort((a, b) => new Date(b.start_time) - new Date(a.start_time));

  if (gecmisim.length === 0) {
    list.innerHTML = '<div class="empty-state">Henüz hiç rezervasyon yapmadınız.</div>';
    return;
  }

  const simdi = new Date();

  gecmisim.forEach((r) => {
    const gelecekte = new Date(r.end_time.replace("Z", "") + "Z") >= simdi;
    const item = document.createElement("div");
    item.className = "reservation-item";
    item.innerHTML = `
      <div class="info">
        <strong>${r.baslik}</strong>
        <span>${roomAdi(r.room_id)} · ${formatTarih(r.start_time)} · ${formatSaat(r.start_time)}-${formatSaat(r.end_time)} · ${r.katilimci_sayisi} kişi</span>
        <span>Oluşturulma: ${formatOlusturmaZamani(r.created_at)}${gelecekte ? "" : " · <em>geçmiş</em>"}</span>
      </div>
      ${gelecekte ? `<button class="btn btn-sm btn-danger" data-res-id="${r.id}">İptal Et</button>` : ""}
    `;
    if (gelecekte) {
      item.querySelector("button").addEventListener("click", () => cancelReservationFromHistory(r.id));
    }
    list.appendChild(item);
  });
}

async function cancelReservationFromHistory(id) {
  if (!confirm("Bu rezervasyonu iptal etmek istediğinize emin misiniz?")) return;
  try {
    await api(`/reservations/${id}`, { method: "DELETE" });
    await Promise.all([loadReservations(), loadGecmisim()]);
    renderReservations();
    renderGecmisim();
  } catch (err) {
    showAlert("app-alert", "İptal edilemedi: " + err.message);
  }
}

// ---------- Rezervasyon oluşturma modalı ----------

function openReservationModal(roomId) {
  clearAlert("modal-alert");
  el("modal-suggestions").innerHTML = "";
  el("res-room").value = roomId || "";
  el("res-baslik").value = "";
  el("res-katilimci").value = "";
  el("res-date").value = "";
  el("res-start").value = "";
  el("res-end").value = "";
  el("reservation-modal").classList.remove("hidden");
}

function closeReservationModal() {
  el("reservation-modal").classList.add("hidden");
}

async function handleCreateReservation(ev) {
  ev.preventDefault();
  clearAlert("modal-alert");
  el("modal-suggestions").innerHTML = "";

  const roomId = el("res-room").value;
  const date = el("res-date").value;
  const start = el("res-start").value;
  const end = el("res-end").value;

  if (!roomId || !date || !start || !end) {
    showAlert("modal-alert", "Lütfen tüm alanları doldurun.");
    return;
  }

  const payload = {
    room_id: parseInt(roomId, 10),
    baslik: el("res-baslik").value.trim(),
    katilimci_sayisi: parseInt(el("res-katilimci").value, 10),
    start_time: `${date}T${start}:00`,
    end_time: `${date}T${end}:00`,
  };

  try {
    await api("/reservations", { method: "POST", body: payload });
    closeReservationModal();
    await loadReservations();
    renderReservations();
  } catch (err) {
    // Backend'den gelen ham JSON yerine okunabilir mesajı gosteriyoruz
    showAlert("modal-alert", err.message);

    const hataKodu = err.payload && err.payload.error;
    if (hataKodu === "conflict" || hataKodu === "capacity_exceeded") {
      await sunAlternatifler(payload, hataKodu);
    }
  }
}

// ---------- Alternatif oda/saat onerisi ----------

function saatToDk(saatStr) {
  const [h, m] = saatStr.split(":").map(Number);
  return h * 60 + m;
}

function dkToSaat(dk) {
  const h = Math.floor(dk / 60);
  const m = dk % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** Bir odanin verilen gundeki bos araliklarini (08:00-18:00 icinde) hesaplar. */
function odaBosAraliklari(roomId, oGunRezervasyonlari) {
  const meşgul = oGunRezervasyonlari
    .filter((r) => r.room_id === roomId)
    .map((r) => [saatToDk(r.start_time.slice(11, 16)), saatToDk(r.end_time.slice(11, 16))])
    .sort((a, b) => a[0] - b[0]);

  const bosluklar = [];
  let imlec = WORK_START;
  meşgul.forEach(([s, e]) => {
    if (s > imlec) bosluklar.push([imlec, s]);
    imlec = Math.max(imlec, e);
  });
  if (imlec < WORK_END) bosluklar.push([imlec, WORK_END]);
  return bosluklar;
}

/** Bir bosluk icinde, verilen sureye sigan 15dk'ya hizali tum baslangic saatlerini dondurur. */
function siganBaslangiclar(bosluk, sureDk) {
  const sonuc = [];
  let s = Math.ceil(bosluk[0] / 15) * 15;
  while (s + sureDk <= bosluk[1]) {
    sonuc.push(s);
    s += 15;
  }
  return sonuc;
}

async function sunAlternatifler(payload, hataKodu) {
  const date = payload.start_time.split("T")[0];
  const istenenBaslangic = saatToDk(payload.start_time.slice(11, 16));
  const istenenBitis = saatToDk(payload.end_time.slice(11, 16));
  const sureDk = istenenBitis - istenenBaslangic;
  const katilimci = payload.katilimci_sayisi;
  const secilenOda = state.rooms.find((r) => r.id === payload.room_id);

  let gununRezervasyonlari;
  try {
    gununRezervasyonlari = await api(`/reservations?date=${date}`);
  } catch (e) {
    return; // oneri sunulamiyor, sessizce vazgec
  }

  let adaylar = [];
  let mod = "kat"; // "kat" = ayni kat farkli saat/oda, "kapasite" = herhangi kat, ayni saat

  if (hataKodu === "conflict" && secilenOda) {
    // 1. adim: ayni kattaki, yeterli kapasiteli odalarda en yakin bos saati ara
    const ayniKatOdalari = state.rooms.filter(
      (r) => r.konum === secilenOda.konum && r.kapasite >= katilimci
    );

    ayniKatOdalari.forEach((room) => {
      odaBosAraliklari(room.id, gununRezervasyonlari).forEach((bosluk) => {
        siganBaslangiclar(bosluk, sureDk).forEach((baslangic) => {
          adaylar.push({
            roomId: room.id,
            baslangic,
            fark: Math.abs(baslangic - istenenBaslangic),
          });
        });
      });
    });
    adaylar.sort((a, b) => a.fark - b.fark);
  }

  if (adaylar.length === 0) {
    // 2. adim (ya da capacity_exceeded icin direkt): herhangi bir kattan, ayni saatte
    // musait, kapasitesi yeterli odalari kapasiteye gore artan sirala
    mod = "kapasite";
    const digerOdalar = state.rooms
      .filter((r) => r.kapasite >= katilimci && r.id !== payload.room_id)
      .sort((a, b) => a.kapasite - b.kapasite);

    digerOdalar.forEach((room) => {
      const uygun = odaBosAraliklari(room.id, gununRezervasyonlari).some(
        (bosluk) => istenenBaslangic >= bosluk[0] && istenenBitis <= bosluk[1]
      );
      if (uygun) {
        adaylar.push({ roomId: room.id, baslangic: istenenBaslangic, fark: 0 });
      }
    });
  }

  renderAlternatifler(adaylar.slice(0, 5), mod, sureDk, date);
}

function renderAlternatifler(adaylar, mod, sureDk, date) {
  const box = el("modal-suggestions");
  if (adaylar.length === 0) {
    box.innerHTML = '<div class="suggestion-empty">Bu gün için uygun bir alternatif bulunamadı, farklı bir tarih deneyebilirsiniz.</div>';
    return;
  }

  const baslik =
    mod === "kat"
      ? "Aynı kattan en yakın uygun saat:"
      : "Bu saatte müsait, yeterli kapasiteli diğer odalar:";

  const liste = adaylar
    .map((a) => {
      const room = state.rooms.find((r) => r.id === a.roomId);
      const bitisDk = a.baslangic + sureDk;
      const etiket =
        mod === "kat"
          ? `${room.ad} (${floorLabel(room.konum)}) · ${dkToSaat(a.baslangic)}-${dkToSaat(bitisDk)}`
          : `${room.ad} (${floorLabel(room.konum)}, ${room.kapasite} kişi) · ${dkToSaat(a.baslangic)}-${dkToSaat(bitisDk)}`;
      return `<button type="button" class="suggestion-item" data-room="${a.roomId}" data-start="${dkToSaat(a.baslangic)}" data-end="${dkToSaat(bitisDk)}">${etiket}</button>`;
    })
    .join("");

  box.innerHTML = `<div class="suggestion-title">${baslik}</div><div class="suggestion-list">${liste}</div>`;

  box.querySelectorAll(".suggestion-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      el("res-room").value = btn.dataset.room;
      el("res-start").value = btn.dataset.start;
      el("res-end").value = btn.dataset.end;
      clearAlert("modal-alert");
      box.innerHTML = "";
    });
  });
}

// ---------- Sekmeler (Odalar / Rezervasyonlarım) ----------

function initAppTabs() {
  el("tab-rooms-btn").addEventListener("click", () => switchAppTab("rooms"));
  el("tab-find-btn").addEventListener("click", () => switchAppTab("find"));
  el("tab-favorites-btn").addEventListener("click", () => switchAppTab("favorites"));
  el("tab-reservations-btn").addEventListener("click", () => switchAppTab("reservations"));
  el("tab-history-btn").addEventListener("click", () => switchAppTab("history"));
  el("tab-stats-btn").addEventListener("click", () => switchAppTab("stats"));
  el("tab-admin-btn").addEventListener("click", () => switchAppTab("admin"));
}

async function switchAppTab(which) {
  const tabs = {
    rooms: { btn: "tab-rooms-btn", panel: "panel-rooms" },
    find: { btn: "tab-find-btn", panel: "panel-find" },
    favorites: { btn: "tab-favorites-btn", panel: "panel-favorites" },
    reservations: { btn: "tab-reservations-btn", panel: "panel-reservations" },
    history: { btn: "tab-history-btn", panel: "panel-history" },
    stats: { btn: "tab-stats-btn", panel: "panel-stats" },
    admin: { btn: "tab-admin-btn", panel: "panel-admin" },
  };

  Object.entries(tabs).forEach(([key, { btn, panel }]) => {
    el(btn).classList.toggle("active", key === which);
    el(panel).classList.toggle("hidden", key !== which);
  });

  if (which === "history") {
    await loadGecmisim();
    renderGecmisim();
  } else if (which === "favorites") {
    await loadFavorites();
    renderFavorites();
  } else if (which === "stats") {
    await loadAndRenderMyStats();
  } else if (which === "admin") {
    await loadAndRenderAdminPanel();
  }
}

// ---------- Kişisel istatistikler ----------

function statCard(label, value) {
  return `<div class="stat-card"><div class="stat-value">${value}</div><div class="stat-label">${label}</div></div>`;
}

async function loadAndRenderMyStats() {
  const grid = el("my-stats-grid");
  try {
    const s = await api("/reservations/my-stats");
    const odaBilgisi = s.en_cok_kullandigi_oda
      ? `${s.en_cok_kullandigi_oda.ad} (${s.en_cok_kullandigi_oda.sayi} kez)`
      : "—";
    const ortSure = s.ortalama_toplanti_suresi_dk !== null
      ? `${s.ortalama_toplanti_suresi_dk} dk`
      : "—";

    grid.innerHTML = [
      statCard("Toplam Rezervasyon", s.toplam_rezervasyon),
      statCard("Ortalama Toplantı Süresi", ortSure),
      statCard("En Çok Kullandığınız Oda", odaBilgisi),
    ].join("");
  } catch (err) {
    grid.innerHTML = "";
    showAlert("app-alert", "İstatistikleriniz yüklenemedi: " + err.message);
  }
}

// ---------- Admin paneli ----------

async function loadAndRenderAdminPanel() {
  try {
    const [overview, rooms, departments, time] = await Promise.all([
      api("/admin/stats/overview"),
      api("/admin/stats/rooms"),
      api("/admin/stats/departments"),
      api("/admin/stats/time"),
    ]);
    renderAdminOverview(overview);
    renderAdminRoomsTable(rooms);
    renderAdminDepartmentsTable(departments);
    renderAdminTime(time);
  } catch (err) {
    showAlert("app-alert", "Admin istatistikleri yüklenemedi: " + err.message);
  }
}

function renderAdminOverview(o) {
  el("admin-overview-grid").innerHTML = [
    statCard("Toplam Kullanıcı", o.toplam_kullanici),
    statCard("Aktif Oda", o.aktif_oda_sayisi),
    statCard("Pasif Oda", o.pasif_oda_sayisi),
    statCard("Toplam Rezervasyon", o.toplam_rezervasyon),
    statCard("Bugünkü Rezervasyon", o.bugunku_rezervasyon_sayisi),
    statCard("Son 7 Gün", o.son_7_gun_rezervasyon_sayisi),
  ].join("");
}

function renderAdminRoomsTable(data) {
  const rows = data.tum_odalar
    .map(
      (r) => `
      <tr>
        <td>${r.ad}</td>
        <td>${floorLabel(r.konum)}</td>
        <td>${r.is_active ? "Aktif" : "Pasif"}</td>
        <td>${r.rezervasyon_sayisi}</td>
      </tr>`
    )
    .join("");

  el("admin-rooms-table").innerHTML = `
    <thead><tr><th>Oda</th><th>Konum</th><th>Durum</th><th>Rezervasyon</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="4" class="empty-state">Kayıt yok</td></tr>'}</tbody>
  `;
}

function renderAdminDepartmentsTable(data) {
  const rows = data
    .map(
      (d) => `
      <tr><td>${d.departman}</td><td>${d.kullanici_sayisi}</td><td>${d.rezervasyon_sayisi}</td></tr>`
    )
    .join("");

  el("admin-departments-table").innerHTML = `
    <thead><tr><th>Departman</th><th>Kullanıcı Sayısı</th><th>Rezervasyon</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="3" class="empty-state">Kayıt yok</td></tr>'}</tbody>
  `;
}

function renderAdminTime(t) {
  const enYogunSaat = t.en_yogun_saat ? `${t.en_yogun_saat.saat} (${t.en_yogun_saat.sayi})` : "—";
  const enYogunGun = t.en_yogun_gun ? `${t.en_yogun_gun.gun} (${t.en_yogun_gun.sayi})` : "—";

  el("admin-time-grid").innerHTML = [
    statCard("En Yoğun Saat", enYogunSaat),
    statCard("En Yoğun Gün", enYogunGun),
  ].join("");
}

// ---------- Karanlık Mod ----------

function initThemeToggle() {
  const THEME_KEY = "rezerv-theme";
  const btn = el("theme-toggle-btn");
  const saved = localStorage.getItem(THEME_KEY);

  if (saved === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
    btn.textContent = "☀️";
  }

  btn.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    if (isDark) {
      document.documentElement.removeAttribute("data-theme");
      localStorage.setItem(THEME_KEY, "light");
      btn.textContent = "🌙";
    } else {
      document.documentElement.setAttribute("data-theme", "dark");
      localStorage.setItem(THEME_KEY, "dark");
      btn.textContent = "☀️";
    }
  });
}

// ---------- Başlangıç ----------

function init() {
  initAuthTabs();
  initAppTabs();
  initThemeToggle();
  renderEkipmanCheckboxes();

  el("form-login").addEventListener("submit", handleLogin);
  el("form-register").addEventListener("submit", handleRegister);
  el("logout-btn").addEventListener("click", handleLogout);
  el("form-reservation").addEventListener("submit", handleCreateReservation);
  el("modal-cancel-btn").addEventListener("click", closeReservationModal);
  el("new-reservation-btn").addEventListener("click", () => openReservationModal(null));
  el("room-search").addEventListener("input", renderRooms);
  el("form-find").addEventListener("submit", handleFindSubmit);

  // sayfa acilirken bugunden onceki tarihleri secilemez yap
  const today = new Date().toISOString().split("T")[0];
  el("res-date").setAttribute("min", today);
  el("find-date").setAttribute("min", today);
}

document.addEventListener("DOMContentLoaded", init);