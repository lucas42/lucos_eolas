class LanguageSelector extends HTMLElement {
	constructor() {
		super();
		const shadow = this.attachShadow({mode: 'closed'});
		const languages = JSON.parse(this.getAttribute("languages"));
		const currentLanguage = this.getAttribute("current-language");
		const endpoint = this.getAttribute("endpoint");
		const csrfToken = document.cookie
			.split('; ')
			.find((row) => row.startsWith('csrftoken='))
			?.split('=')[1];

		const style = document.createElement('style');
		style.textContent = `
			:host {
				float: right;
				font-size: smaller;
				color: var(--lang-disabled)
			}
			a {
				cursor: pointer;
				font-weight: normal;
				text-decoration: none;
			}
			a:hover {
				text-decoration: underline;
			}
			a.current {
				font-weight: bold;
				color: var(--lang-enabled);
			}
			a.loading {
				opacity: 0.2;
				cursor: wait;
			}
		`;
		shadow.append(style);

		const languageList = document.createElement('span');

		languages.forEach(language => {
			if (languageList.firstChild) languageList.append(" | ");
			const languageLink = document.createElement('a');
			languageLink.append(language.code);
			languageLink.setAttribute("title", language.name_local);
			const isCurrent = (language.code == currentLanguage);
			if (isCurrent) languageLink.classList.add("current");
			languageLink.addEventListener("click", async event => {
				languageLink.classList.add("loading");
				await fetch(endpoint, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/x-www-form-urlencoded',
						'X-CSRFToken': csrfToken,
					},
					body: `language=${language.code}`,
				});
				navigation.reload();

				/* 
					TODO: Could probably do some more error handling here.
					However, django's setlang endpoint tends to fail silently,
					so quite hard to detect.
				*/
			});
			languageList.append(languageLink);
		});

		shadow.append(languageList);
	}
}
customElements.define('language-selector', LanguageSelector);