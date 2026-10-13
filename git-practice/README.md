# Git 연습 폴더

브랜치 → 커밋 → 푸시 → PR → 풀을 한 번씩 해 보는 곳이에요. 여기 파일은 실제 앱과 상관없고, 연습이 끝나면 폴더째 지워요.

## 순서

1. 최신 상태 받기

```bash
git checkout main
git pull
```

2. 내 브랜치 만들기 (이름은 영어로)

```bash
git checkout -b practice/내이름
```

3. 이 폴더에 `내이름.md` 파일을 만들고 자기소개 한 줄 쓰기

4. 커밋하기

```bash
git add git-practice/내이름.md
git commit -m "git 연습: 내이름 추가"
```

5. 푸시하기

```bash
git push -u origin practice/내이름
```

6. GitHub에서 **Pull Request** 만들기 → 팀원 1명에게 리뷰 받고 머지

7. 다른 사람 PR이 머지되면 다시 받아 보기

```bash
git checkout main
git pull
```

이 폴더에 다른 팀원들 파일이 보이면 성공이에요.

## 충돌 연습 (선택)

두 명이 같은 줄을 고쳐 보면 충돌이 나요. 아래 줄을 각자 브랜치에서 다르게 고친 뒤 차례로 PR을 머지해 보세요.

오늘의 점심 메뉴: (여기를 고치세요)
