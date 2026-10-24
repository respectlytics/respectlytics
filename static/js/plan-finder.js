/**
 * The plan slider (billing/_plan_finder.html), on the pricing page and the plan page alike.
 *
 * The slider picks a plan by the events it holds and shows that plan's card; the period switch
 * shows every price, and every mark of the current plan, for its own period. On the plan page
 * the buy box follows: the plan and the period travel into Checkout, and it hides on the free
 * plan and on Enterprise, which have no checkout, and its button names the plan ("Continue with
 * the Business plan"), never just "Business", which is also a buyer's choice in the same box.
 * The page is rendered in its starting state, so nothing moves when this runs.
 */
(function () {
    'use strict';

    function init(finder) {
        const positions = JSON.parse(document.getElementById('plan-finder-data').textContent);
        const slider = finder.querySelector('#events-slider');
        const value = finder.querySelector('#slider-value');
        const cards = finder.querySelectorAll('.pricing-card');
        const form = finder.querySelector('#checkout-form');
        const button = finder.querySelector('[data-checkout-button]');
        const monthly = finder.querySelector('#monthly-btn');
        const annual = finder.querySelector('#annual-btn');
        const deployment = document.querySelector('[data-deployment-card]');
        let period = finder.dataset.initialPeriod === 'annual' ? 'annual' : 'monthly';

        function showPlan() {
            const position = positions[parseInt(slider.value, 10)] || positions[0];
            const enterprise = position.slug === 'enterprise';
            value.textContent = position.display;
            slider.setAttribute('aria-valuetext', `${position.display} events a month: ${position.name}`);
            slider.style.setProperty('--fill', `${(slider.value / slider.max) * 100}%`);
            cards.forEach(card => card.classList.toggle('hidden', card.dataset.plan !== position.slug));
            if (form) {
                const buyable = position.slug !== 'free' && !enterprise;
                form.classList.toggle('hidden', !buyable);
                form.elements.plan.value = buyable ? position.slug : '';
                if (button && buyable) button.textContent = `Continue with the ${position.name} plan`;
            }
            if (deployment) {
                deployment.classList.toggle('border-brand-400/40', enterprise);
                deployment.classList.toggle('border-white/[0.07]', !enterprise);
            }
        }

        function showPeriod() {
            [[monthly, 'monthly'], [annual, 'annual']].forEach(([toggle, own]) => {
                toggle.classList.toggle('active', period === own);
                toggle.setAttribute('aria-pressed', String(period === own));
            });
            finder.querySelectorAll('[data-period]').forEach(element => {
                element.classList.toggle('hidden', element.dataset.period !== period);
            });
            if (form) form.elements.period.value = period;
        }

        slider.addEventListener('input', showPlan);
        monthly.addEventListener('click', () => { period = 'monthly'; showPeriod(); });
        annual.addEventListener('click', () => { period = 'annual'; showPeriod(); });
        showPlan();
        showPeriod();
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-plan-finder]').forEach(init);
    });
})();
