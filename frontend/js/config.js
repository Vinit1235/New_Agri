/*
 * SoilEdge Frontend Config — Single Source of Truth
 *
 * Loads once and provides:
 *   - API_BASE: the backend base URL
 *   - Token helpers: saveToken / getToken / clearToken
 *   - Field management: fetches user's fields, populates a universal
 *     dropdown in the navbar, and stores the active field ID in localStorage
 *
 * Every page that needs backend access should include this script BEFORE
 * any page-specific script:
 *
 *     <script src="js/config.js"></script>
 *     <script> ... page logic ... </script>
 */
const API_BASE = 'http://localhost:8000';
const TOKEN_KEY = 'krishi_token';
const USER_KEY = 'krishi_user';
const FIELD_KEY = 'current_field_id';

// ---------------------------------------------------------------------------
// Token management
// ---------------------------------------------------------------------------
function saveToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
}

function getUserId() {
    return localStorage.getItem(USER_KEY);
}

// ---------------------------------------------------------------------------
// Auth guard — redirect to login if no token
// ---------------------------------------------------------------------------
function requireAuth() {
    const token = getToken();
    if (!token) {
        window.location.href = 'login.html';
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// Shared auth headers for fetch calls
// ---------------------------------------------------------------------------
function authHeaders() {
    const token = getToken();
    return {
        'Authorization': token ? `Bearer ${token}` : '',
        'Content-Type': 'application/json',
    };
}

// ---------------------------------------------------------------------------
// Field management — universal dropdown + persistence
// ---------------------------------------------------------------------------
let _fieldsCache = [];

async function loadFields() {
    const res = await fetch(`${API_BASE}/api/fields`, {
        headers: authHeaders(),
    });
    if (!res.ok) return [];
    const fields = await res.json();
    _fieldsCache = fields;
    return fields;
}

function currentFieldId() {
    const stored = localStorage.getItem(FIELD_KEY);
    if (stored) return parseInt(stored, 10);
    // fall back to first field when available
    const first = _fieldsCache[0];
    return first ? first.id : 1;
}

function setCurrentFieldId(id) {
    localStorage.setItem(FIELD_KEY, String(id));
}

// Populate the #fieldSwitcher dropdown (or .field-switcher) with the user's
// fields, mark the current one as selected, and wire up change events.
async function populateFieldSwitcher() {
    const fields = await loadFields();

    // look for the dropdown element by id, or by class
    const dropdown = document.getElementById('fieldSwitcher')
        || document.querySelector('.field-switcher')
        || document.querySelector('select[name="field"]');

    if (!dropdown) return;

    // remember current selection before we wipe options
    const prev = currentFieldId();

    dropdown.innerHTML = '';
    fields.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f.id;
        opt.textContent = f.name || `Field #${f.id}`;
        if (f.id === prev) opt.selected = true;
        dropdown.appendChild(opt);
    });

    // if no field was persisted and we have at least one, pick the first
    if (!localStorage.getItem(FIELD_KEY) && fields.length) {
        setCurrentFieldId(fields[0].id);
    }

    dropdown.addEventListener('change', () => {
        const val = parseInt(dropdown.value, 10);
        setCurrentFieldId(val);
        // trigger a re-fetch — pages should listen for this event
        window.dispatchEvent(new CustomEvent('fieldChanged', {
            detail: { fieldId: val }
        }));
    });
}

// Boot: attach a universal field switcher to every page that has one.
// Run on DOMContentLoaded so the element exists.
document.addEventListener('DOMContentLoaded', () => {
    populateFieldSwitcher();
});
