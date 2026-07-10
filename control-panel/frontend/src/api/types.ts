import type { AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios';

/** 后端统一响应结构，可按实际接口调整 */
export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

export type RequestConfig = AxiosRequestConfig;

export type RequestInterceptor = (
  config: InternalAxiosRequestConfig,
) => InternalAxiosRequestConfig | Promise<InternalAxiosRequestConfig>;

export type ResponseInterceptor = (response: AxiosResponse) => AxiosResponse | Promise<AxiosResponse>;
