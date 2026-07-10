import axios from 'axios';
import type { AxiosRequestConfig } from 'axios';
import type { ApiResponse } from './types';

const instance = axios.create({
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
});

instance.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error),
);

instance.interceptors.response.use(
  (response) => {
    const payload = response.data as ApiResponse;

    if (payload && typeof payload === 'object' && 'code' in payload && payload.code !== 0) {
      return Promise.reject(new Error(payload.message || '请求失败'));
    }

    return response;
  },
  (error) => {
    const message = error.response?.data?.message || error.message || '网络异常';
    return Promise.reject(new Error(message));
  },
);

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
