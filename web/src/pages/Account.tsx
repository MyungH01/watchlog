import { api, Me } from "../api";

/** 로그인(계정): 구글 계정 연결, 로그아웃, 내 데이터 삭제. 계정에 관한 것만 이 화면에 둔다. */
export function Account({ me }: { me: Me }) {
  async function wipe() {
    if (!confirm("모든 시계, 기록, 사진을 삭제합니다. 되돌릴 수 없습니다. 계속할까요?")) return;
    await api.deleteMe();
    location.href = "/";
  }
  async function logout() {
    await api.logout();
    location.href = "/";
  }

  return (
    <>
      {me.anonymous ? (
        <section className="panel">
          <h2>로그인</h2>
          <p className="sub">
            로그인하지 않아도 모든 기능을 쓸 수 있습니다. 다만 기록이 이 브라우저에만 연결돼 있어서,
            브라우저 데이터를 지우거나 다른 기기에서 열면 다시 볼 수 없습니다.
          </p>
          <p className="sub">구글 계정으로 로그인하면 지금까지의 기록이 그 계정에 보관되고, 다른 기기에서도 볼 수 있습니다. 처음이라면 가입도 함께 이루어집니다.</p>
          {me.google_enabled ? (
            <a className="primary wide" href="/api/auth/google/login">구글 계정으로 계속하기</a>
          ) : (
            <>
              <button className="primary wide" disabled>구글 계정으로 계속하기</button>
              <p className="footnote">구글 로그인은 아직 연결되지 않았습니다. 서버에 구글 설정을 넣으면 이 버튼이 켜집니다.</p>
            </>
          )}
        </section>
      ) : (
        <section className="panel">
          <h2>계정</h2>
          <p className="sub"><b>{me.email}</b> 계정으로 로그인돼 있습니다. 다른 기기에서도 같은 계정으로 로그인하면 컬렉션을 볼 수 있습니다.</p>
          <button className="ghost wide" onClick={logout}>로그아웃</button>
        </section>
      )}

      <section className="panel">
        <h2>내 데이터 삭제</h2>
        <p className="sub">등록한 시계, 측정 기록, 사진을 서버에서 모두 삭제합니다. 녹음은 분석이 끝나면 바로 지워져 남아 있지 않습니다.</p>
        <button className="danger wide" onClick={wipe}>내 데이터 전체 삭제</button>
      </section>
    </>
  );
}
