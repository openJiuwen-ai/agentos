import axios from 'axios';
import type { AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios';
import type { ApiResponse } from './types';

/** HTTP 错误：携带状态码，供调用方按 status 精确判别（如 503 未配置）。 */
export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const instance = axios.create({
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ── request: attach access token ──
instance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// ── response: handle 401 with token refresh ──
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error);
    } else {
      resolve(token);
    }
  });
  failedQueue = [];
}

instance.interceptors.response.use(
  (response) => {
    const payload = response.data as ApiResponse;

    if (payload && typeof payload === 'object' && 'code' in payload && payload.code >= 400) {
      return Promise.reject(new Error(payload.message || '请求失败'));
    }

    return response;
  },
  async (error) => {
    // 取消的请求归一化为 message='canceled'，避免 fetch adapter 下 message
    // 随环境变化（'This operation was aborted' 等）导致页面取消判断失效。
    if (axios.isCancel(error)) {
      return Promise.reject(new Error('canceled'));
    }

    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // Only attempt refresh on 401, not on the refresh/login endpoints themselves
    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/refresh') &&
      !originalRequest.url?.includes('/auth/login')
    ) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
          }
          return instance(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = localStorage.getItem('refresh_token');
      if (!refreshToken) {
        isRefreshing = false;
        clearAuth();
        window.location.href = '/login';
        return Promise.reject(new Error('请重新登录'));
      }

      try {
        const { data } = await axios.post('/api/v1/auth/refresh', { refresh_token: refreshToken });
        const newAccess = data.data?.access_token || data.access_token;
        const newRefresh = data.data?.refresh_token || data.refresh_token;

        localStorage.setItem('access_token', newAccess);
        if (newRefresh) {
          localStorage.setItem('refresh_token', newRefresh);
        }

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${newAccess}`;
        }

        processQueue(null, newAccess);
        return instance(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        clearAuth();
        window.location.href = '/login';
        return Promise.reject(new Error('登录已过期，请重新登录'));
      } finally {
        isRefreshing = false;
      }
    }

    const message = error.response?.data?.detail || error.response?.data?.message || error.message || '网络异常';
    return Promise.reject(new ApiError(message, error.response?.status));
  },
);

function clearAuth() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('username');
  localStorage.removeItem('role');
  localStorage.removeItem('workspace');
}

function unwrap<T>(response: { data: ApiResponse<T> | T }): T {
  const { data } = response;

  if (data && typeof data === 'object' && 'data' in data) {
    return (data as ApiResponse<T>).data;
  }

  return data as T;
}

export function get<T = unknown>(url: string, params?: object, config?: AxiosRequestConfig) {
  return instance.get<ApiResponse<T>>(url, { params, ...config }).then(unwrap);
}

export function post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) {
  return instance.post<ApiResponse<T>>(url, data, config).then(unwrap);
}

export function put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) {
  return instance.put<ApiResponse<T>>(url, data, config).then(unwrap);
}

export function patch<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) {
  return instance.patch<ApiResponse<T>>(url, data, config).then(unwrap);
}

export function del<T = unknown>(url: string, params?: object, config?: AxiosRequestConfig) {
  return instance.delete<ApiResponse<T>>(url, { params, ...config }).then(unwrap);
}

export { instance as http };
