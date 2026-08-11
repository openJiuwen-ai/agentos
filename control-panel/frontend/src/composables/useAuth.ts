import { ref, computed } from 'vue';

const accessToken = ref(localStorage.getItem('access_token') || '');
const refreshToken = ref(localStorage.getItem('refresh_token') || '');
const username = ref(localStorage.getItem('username') || '');
const userId = ref(localStorage.getItem('user_id') || '');
const role = ref(localStorage.getItem('role') || 'user');
const workspace = ref<'admin' | 'user'>(localStorage.getItem('workspace') === 'user' ? 'user' : 'admin');

export function useAuth() {
  const isAdmin = computed(() => role.value === 'admin');
  const effectiveIsAdmin = computed(() => isAdmin.value && workspace.value !== 'user');
  const isLoggedIn = computed(() => !!accessToken.value);

  function setWorkspace(mode: 'admin' | 'user') {
    workspace.value = mode;
    localStorage.setItem('workspace', mode);
  }

  function storeAuth(auth: {
    access_token: string;
    refresh_token: string;
    user_id: string;
    username: string;
    role: string;
  }) {
    accessToken.value = auth.access_token;
    refreshToken.value = auth.refresh_token;
    userId.value = auth.user_id;
    username.value = auth.username;
    role.value = auth.role;
    workspace.value = 'admin';

    localStorage.setItem('access_token', auth.access_token);
    localStorage.setItem('refresh_token', auth.refresh_token);
    localStorage.setItem('user_id', auth.user_id);
    localStorage.setItem('username', auth.username);
    localStorage.setItem('role', auth.role);
    localStorage.setItem('workspace', 'admin');
  }

  function clearAuth() {
    accessToken.value = '';
    refreshToken.value = '';
    userId.value = '';
    username.value = '';
    role.value = 'user';

    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    localStorage.removeItem('workspace');
    workspace.value = 'admin';
  }

  return {
    accessToken,
    refreshToken,
    userId,
    username,
    role,
    workspace,
    isAdmin,
    effectiveIsAdmin,
    isLoggedIn,
    storeAuth,
    setWorkspace,
    clearAuth,
  };
}
