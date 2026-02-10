import axios from 'axios';
import { getAuthHeader } from '../../store/AuthContext';

export const httpClient = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

httpClient.interceptors.request.use((config) => {
  const authHeader = getAuthHeader();
  if (authHeader.Authorization) {
    config.headers.Authorization = authHeader.Authorization;
  }
  return config;
});

httpClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      window.dispatchEvent(new Event('auth:unauthorized'));
    }
    return Promise.reject(error);
  }
);
