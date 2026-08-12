# Challenge

> Most of Belda and Bink's plans are visible to everyone. Someone involved in the handmade details knows a bit more. What is it?

<p align="center">
  <img src="challenge-site.png" alt="Something Handmade challenge page" width="560">
</p>

<https://www.zola.com/wedding/beldaandbink>

This challenge was one of the harder OSINT challenges I've solved, and I was freaking out when I finally got the flag... mainly because I think I overcomplicated it and there was probably an easier way.


<strong>My reaction and explanation to my teammate</strong>
<br>

This was my reaction when solving it:

<p align="center">
  <img src="image-20.png" alt="reaction text message" width="520">
</p>

And this was my explanation to my teammate (I was high on adrenaline):

<p align="center">
  <img src="image-21.png" alt="teammate explanation screenshot 1" width="32%">
  <img src="image-22.png" alt="teammate explanation screenshot 2" width="32%">
  <img src="image-23.png" alt="teammate explanation screenshot 3" width="32%">
</p>



---

# Flag search process

## Looking Through the Wedding Website

The link takes you to a Zola wedding page. Most of the information didn't seem useful at first glance until I came across this text:

<p align="center">
  <img src="image.png" alt="Zola wedding page handmade details text" width="760">
</p>

This fits the challenge description because it says someone by the name of `@miphamakes` was doing "something handmade."

---

## Finding miphamakes

The natural next step would be to try to find the `@miphamakes` account. I expected this to be a simple Instagram or TikTok account or something, but nothing came up. I then used Sherlock to try to search the major social media networks... still nothing. Then I tried a different username search tool, Maigret, to search the less popular sites.

<p align="center">
  <img src="image-1.png" alt="Sherlock username search result" width="430">
</p>

<p align="center">
  <img src="image-2-result.png" alt="Maigret username search result" width="720">
</p>

This result had to be the next step... it was made on the day of the CTF challenge and was the only result.

The result takes you to a site called DeviantArt with 3 images posted. I was stuck here for a while. I scanned everyone who favorited/commented on the images but nothing was useful. I also tried downloading the images and doing forensics on them, but nothing came from that.

<p align="center">
  <img src="image-3.png" alt="miphamakes DeviantArt profile" width="900">
</p>

---

## The Three Handmade Posts

I spent a good 30 minutes just scouring the DeviantArt profile trying to find something useful. The actual direction was simpler than expected...

There were 3 images, each with a description:

<p align="center">
  <img src="image-4-clue.png" alt="Triforce Florals description mentioning Tessa" width="760">
</p>

<p align="center">
  <img src="image-5-clue.png" alt="Bout of Doubt description mentioning Nolan" width="760">
</p>

<p align="center">
  <img src="image-6-clue.png" alt="Our Wedding Bags description mentioning Carl" width="760">
</p>

---


<summary><strong>Dead Ends</strong></summary>
<br>

I didn't really know what to do with these 3 names, so before realizing what the three names were for, I tried several other possible paths (the last one was very desperate...)

- Reverse-searching the handmade images
- Examining DeviantArt image metadata
- Looking at watchers, favorites, comments, and badge givers
- Trying to identify the location in the Zola gallery photo
- Searching for possible usernames based on Carl, such as `carlmakes`, `carlcrafts`, and similar variants

The social interactions were very unreliable because DeviantArt is a live platform. Watchers, favorites, comments, and badges could come from just normal users or even other CTF players.

Trying username variants for Carl also produced huge numbers of unrelated real accounts. For example, CarlCrafts led to a random Minecraft YouTube channel.

Then I gave up for a while and went to give "Lost Media" a shot... which also was pretty frustrating (you can find the writeup here: `UIUCTF 2026\Lost Media (OSINT)\Writeup.md`)



---

## The Big Realization

After I came back, I realized that the names were probably guest names at the wedding. There were two reasons for this assumption:

1. The descriptions implied that the names were involved in the wedding.
2. Zola wedding websites have an RSVP system where guests identify themselves by entering their name.

The challenge description said, "Most of Belda and Bink's plans are visible to everyone."

So there are 3 possible guest names: `Carl`, `Tessa`, and `Nolan`.

Now all I had to do was figure out how Zola's guest lookup worked! Easier said than done...

---

## Reverse Engineering Zola's RSVP Search

The Belda and Bink wedding website didn't have an RSVP interface... so I found a random public Zola wedding that had an RSVP page. (https://www.zola.com/wedding/yeseniaandfrank2025/rsvp)

<p align="center">
  <img src="image-8-rsvp.png" alt="Public Zola RSVP guest-name form" width="650">
</p>

I apologize to this couple for stalking their wedding page... but I had to understand how the Zola frontend worked.

I entered a random guest name to see how the network requests worked.

<p align="center">
  <img src="image-9-request.png" alt="Zola RSVP network request" width="800">
</p>

This was very interesting... the request format was:

```http
POST /web-api/v1/publicwedding/rsvp/guest/wedding-account/uuid/<WEDDING_UUID>/search-groups
```

The payload was extremely simple:

```json
{
  "guest_name": "zzzztestperson"
}
```

The response was:

```json
[]
```

So this was how Zola's public RSVP guest search worked.

---

### Getting the UUID of Belda and Bink

This was pretty simple... just inspecting the page source of the wedding page.

I got a little lazy because there were so many instances of "UUID," and I was not about to search all 49 of them.

<p align="center">
  <img src="image-11.png" alt="Searching page source for uuid" width="44%">
</p>

So I copy-pasted the whole page source into ChatGPT and asked it to get the account UUID:

<p align="center">
  <img src="image-12-uuid.png" alt="ChatGPT finding wedding account UUID and ID" width="760">
</p>

It found it:

|  |  |
|---|---|
| **Wedding Account ID:** | `5170610` |
| **Wedding Account UUID:** | `98298caa-11a9-4c3e-83c2-197f59ec8235` |

---

### Reproducing Guest Search

I first tried calling the endpoint directly from the DevTools console.

The initial request returned:

```text
403 Forbidden
Invalid request
```

<p align="center">
  <img src="image-13.png" alt="403 Forbidden invalid request in DevTools" width="760">
</p>

Comparing the manual request with the legitimate browser request showed that the original request contained an `x-csrf-token` header.

The CSRF value could be read from Zola's `CSRF-TOKEN` cookie:

```js
const csrf = decodeURIComponent(
  document.cookie
    .split("; ")
    .find(x => x.startsWith("CSRF-TOKEN="))
    ?.split("=")[1] || ""
);

console.log(csrf);
```

<p align="center">
  <img src="image-14.png" alt="CSRF token read from cookie" width="381">
</p>

Then I created a helper:

```js
async function searchGuest(uuid, name) {
  const r = await fetch(
    `https://www.zola.com/web-api/v1/publicwedding/rsvp/guest/wedding-account/uuid/${uuid}/search-groups`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-csrf-token": csrf
      },
      credentials: "include",
      body: JSON.stringify({
        guest_name: name
      })
    }
  );

  const text = await r.text();

  console.log({
    name,
    status: r.status,
    response: text
  });
}
```

I tested it:

```js
searchGuest(
  "98298caa-11a9-4c3e-83c2-197f59ec8235",
  "zzzztestperson"
);
```

<p align="center">
  <img src="image-15.png" alt="Successful test guest search" width="760">
</p>

Result:

```text
status: 200
response: []
```

This meant that the request was reproduced correctly and the challenge wedding supported the same guest-search API!

---

### Searching the Names From DeviantArt

I then tried searching the 3 names from the descriptions to see if they appeared on the RSVP guest list for the challenge website.

<p align="center">
  <img src="image-16.png" alt="Searching Carl Tessa and Nolan through Zola guest search" width="760">
</p>

The three names from the posts were actual guests in the challenge wedding!!

---

### Gathering More Info

The `search-groups` endpoint only gave names and UUIDs. We still needed to know what wedding information each guest could see.

Instead of guessing endpoints, I inspected Zola's own frontend JavaScript. I searched for `search-groups` and found this:

This was the function Zola calls when searching for a guest:

```ts
export function getRsvpByGuestGroupUuidV2(
  guestGroupUuid: string
): AppThunk<Promise> {
  return (dispatch, getState) => {
    dispatch(requestGuestRsvp());

    const weddingAccountUuid =
      getState().publicWebsite.wedding.wedding_account_uuid;

    return ApiService.get(
      `/web-api/v2/publicwedding/rsvp/guest-group/uuid/${guestGroupUuid}/wedding-account/uuid/${weddingAccountUuid}`
    ).then((response) => {
      ...
    });
  };
}
```

So the read-only endpoint was:

```http
GET /web-api/v2/publicwedding/rsvp/guest-group/uuid/<GROUP_UUID>/wedding-account/uuid/<WEDDING_UUID>
```

---

### Reading the Guest's Wedding Events

I made another helper:

```js
async function getRsvp(groupUuid) {
  const weddingUuid =
    "98298caa-11a9-4c3e-83c2-197f59ec8235";

  const r = await fetch(
    `https://www.zola.com/web-api/v2/publicwedding/rsvp/guest-group/uuid/${groupUuid}/wedding-account/uuid/${weddingUuid}`,
    {
      method: "GET",
      credentials: "include"
    }
  );

  const text = await r.text();

  console.log({
    status: r.status,
    response: text
  });

  return text;
}
```

Then I queried all three groups:

```js
const groups = {
  Carl: "46bdaeb5-ba84-4d91-ad7b-29301af31562",
  Tessa: "f59be3eb-9999-46ec-a6f8-c0668f2d727e",
  Nolan: "57b90e69-9920-420f-9bb1-d6bd52939307"
};

for (const [name, uuid] of Object.entries(groups)) {
  console.log(`===== ${name} =====`);
  await getRsvp(uuid);
}
```

All three requests returned:

```text
200 OK
```

The responses contained:

- `guests`
- `event_invitations`
- `events`
- `meal_options`
- `rsvp_questions`

<p align="center">
  <img src="image-18-results.png" alt="Zola guest RSVP event response" width="900">
</p>

That contained a lot of info... surely the flag had to be somewhere...

Searching for `"uiuctf"` revealed the flag under one of Carl's meals!

<p align="center">
  <img src="image-19.png" alt="Flag found under Carl's meal" width="900">
</p>

> **Flag:** `uiuctf{handmade_with_a_hidden_detail_7c4e1d}`
