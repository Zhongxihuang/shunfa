const app = getApp();

// Track whether we're already retrying a request to prevent infinite loops
const _pendingRetry = new Set();

const request = (url, method, data) => {
  return new Promise((resolve, reject) => {
    const token = app.globalData.token;
    const doRequest = () => {
      wx.request({
        url: `${app.globalData.baseUrl}${url}`,
        method: method || 'GET',
        data: data || {},
        header: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        success: (res) => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(res.data);
          } else if (res.statusCode === 401 && !_pendingRetry.has(url)) {
            // Token expired — attempt re-login once
            _pendingRetry.add(url);
            const auth = require('./auth');
            auth.login().then(() => {
              _pendingRetry.delete(url);
              // Retry with fresh token
              const newToken = app.globalData.token;
              wx.request({
                url: `${app.globalData.baseUrl}${url}`,
                method: method || 'GET',
                data: data || {},
                header: {
                  'Content-Type': 'application/json',
                  ...(newToken ? { Authorization: `Bearer ${newToken}` } : {})
                },
                success: (retryRes) => {
                  if (retryRes.statusCode >= 200 && retryRes.statusCode < 300) {
                    resolve(retryRes.data);
                  } else {
                    reject({ statusCode: retryRes.statusCode, data: retryRes.data });
                  }
                },
                fail: (err) => reject({ statusCode: 0, data: { detail: '网络连接失败，请检查网络设置' }, networkError: true })
              });
            }).catch(() => {
              _pendingRetry.delete(url);
              // Re-login failed — show modal and suggest re-enter
              wx.showModal({
                title: '登录已过期',
                content: '请重新进入小程序以继续使用',
                showCancel: false
              });
              reject({ statusCode: 401, data: { detail: '登录已过期' }, expired: true });
            });
          } else {
            reject({ statusCode: res.statusCode, data: res.data });
          }
        },
        fail: (err) => {
          reject({
            statusCode: 0,
            data: { detail: '网络连接失败，请检查网络设置' },
            networkError: true
          });
        }
      });
    };

    doRequest();
  });
};

module.exports = {
  get: (url) => request(url, 'GET'),
  post: (url, data) => request(url, 'POST', data),
  put: (url, data) => request(url, 'PUT', data),
  delete: (url) => request(url, 'DELETE')
};