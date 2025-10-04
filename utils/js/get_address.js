import * as bitcoin from 'bitcoinjs-lib';
import { BIP32Factory } from 'bip32';
import * as bip39 from 'bip39';
import * as ecc from 'tiny-secp256k1';
import { createHash } from 'crypto';
import {Signer} from "./bip322-js/dist/index.js";


bitcoin.initEccLib(ecc);
const bip32 = BIP32Factory(ecc);
const network = bitcoin.networks.testnet;
const mnemonic = "example crash candy gauge soccer artefact dance used goose solid tray trap"; // Або підставити свою
const seed = bip39.mnemonicToSeedSync(mnemonic);
const root = bip32.fromSeed(seed, network);

const path = "m/86'/0'/0'/0/0";
const child = root.derivePath(path);

const { address } = bitcoin.payments.p2tr({
  internalPubkey: child.publicKey.slice(1, 33),
  network,
});

function taggedHash(tag, msg) {
  const tagHash = createHash('sha256').update(tag).digest();
  return createHash('sha256')
    .update(Buffer.concat([tagHash, tagHash, msg]))
    .digest();
}

function signMessage(message, privateKey) {
  const messageHash = taggedHash('TapSighash', Buffer.from(message));
  const signature = ecc.sign(messageHash, privateKey);
  return Buffer.from(signature).toString('base64');
}

function sign_message_bip322(wif, address, message){
    return Signer.sign(wif, address, message);
}


const wif = "cQvp8xYc8MHBQ3hWa4g7sPAbrm5MUuANokNSEF1CEoGdMf5BcZFN"
console.log('WIF', wif)
console.log("Mnemonic:", mnemonic);
console.log("Taproot Address (mainnet):", address);
console.log("Public Key:", Buffer.from(child.publicKey).toString('hex'));
const message = "Please sign this message to prove ownership of your wallet. Unique code: 6484509866465351";
const signature = sign_message_bip322(wif, address, message);
console.log("Signed Message:", signature);