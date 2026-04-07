/**
 * Firebase JS SDK v9+ (모듈) 예시.
 * 실제 값은 Firebase 콘솔 → 프로젝트 설정 → 일반 → 내 앱 에서 복사합니다.
 *
 * 사용: 이 파일을 firebase-config.js 로 복사해 채운 뒤, firebase-config.js 는 Git에 올리지 마세요.
 */
import { initializeApp } from "firebase/app";
import { getAnalytics, isSupported } from "firebase/analytics";

const firebaseConfig = {
  apiKey: "YOUR_WEB_API_KEY",
  authDomain: "YOUR_PROJECT.firebaseapp.com",
  projectId: "YOUR_PROJECT_ID",
  storageBucket: "YOUR_PROJECT.firebasestorage.app",
  messagingSenderId: "YOUR_SENDER_ID",
  appId: "YOUR_APP_ID",
  measurementId: "G-XXXXXXXXXX", // Analytics 사용 시에만
};

const app = initializeApp(firebaseConfig);

// Analytics 는 브라우저·환경에 따라 지원 여부가 다름
let analytics = null;
isSupported().then((yes) => {
  if (yes) {
    analytics = getAnalytics(app);
  }
});

export { app, analytics };
