import { useEffect, useState } from "react";
import { api, Me } from "./api";
import { Account } from "./pages/Account";
import { Collection } from "./pages/Collection";
import { Landing } from "./pages/Landing";
import { Measure } from "./pages/Measure";
import { PhotoReading } from "./pages/PhotoReading";
import { SetTime } from "./pages/SetTime";
import { WatchDetail } from "./pages/WatchDetail";
import { WatchForm } from "./pages/WatchForm";

// 화면이 몇 개뿐이라 라우터 라이브러리 없이 주소의 # 뒤쪽으로 구분한다
function useRoute(): string[] {
  const read = () => location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => { setRoute(read()); scrollTo(0, 0); };
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (path: string) => { location.hash = path; };

/** 주요 화면 네 곳(소개, 컬렉션, 시간, 계정)에 공통으로 놓이는 메뉴. 지금 어디에 있는지 표시한다. */
function Nav({ current, me }: { current: "about" | "watches" | "time" | "account"; me: Me }) {
  const items = [["about", "소개"], ["watches", "컬렉션"], ["time", "시간"], ["account", me.anonymous ? "로그인" : "계정"]] as const;
  return (
    <header className="top">
      <button className="wordmark" onClick={() => go("/")}>watchlog</button>
      <nav className="nav" aria-label="주요 메뉴">
        {items.map(([key, label]) => (
          <button key={key} className={current === key ? "on" : ""} aria-current={current === key ? "page" : undefined} onClick={() => go(`/${key}`)}>
            {label}
          </button>
        ))}
      </nav>
    </header>
  );
}

export function App() {
  const route = useRoute();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.session().then(setMe, () => setError("서버에 연결하지 못했습니다. 잠시 뒤 다시 열어 주세요."));
  }, []);

  if (error) return <main className="shell"><p className="notice bad">{error}</p></main>;
  if (!me) return <main className="shell"><p className="loading">불러오는 중</p></main>;

  const [page, id, sub] = route;
  // 첫 화면("/")은 항상 소개다. settings는 예전 주소
  const main = !page ? "about" : page === "settings" ? "account" : page;
  let view;
  if (main === "about") view = <><Nav current="about" me={me} /><Landing /></>;
  else if (main === "watches") view = <><Nav current="watches" me={me} /><Collection me={me} /></>;
  else if (main === "time") view = <><Nav current="time" me={me} /><SetTime /></>;
  else if (main === "account") view = <><Nav current="account" me={me} /><Account me={me} /></>;
  else if (page === "new") view = <WatchForm />;
  else if (page === "watch" && id && sub === "edit") view = <WatchForm watchId={id} />;
  else if (page === "watch" && id && sub === "measure") view = <Measure watchId={id} />;
  else if (page === "watch" && id && sub === "photo") view = <PhotoReading watchId={id} reset={route[3] === "reset"} />;
  else if (page === "watch" && id) view = <WatchDetail watchId={id} />;
  else view = <><Nav current="watches" me={me} /><Collection me={me} /></>;

  const fit = page === "watch" && id && !sub;   // 시계 상세는 스크롤 없이 한 화면에 맞춘다
  const cls = fit ? "shell fit" : main === "about" ? "shell wide" : "shell";
  return <main className={cls} key={route.join("/")}>{view}</main>;
}
